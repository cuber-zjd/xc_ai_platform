// 只归档/取消已过期的同步单页请求，不处理 crawl、extract 或仍持锁的任务。
const fs = require('fs');
const {getScrapeQueue, redisConnection} = require('/app/dist/src/services/queue-service');

async function main() {
  const queue = getScrapeQueue();
  const cutoff = Date.now() - 3600000;
  const eligible = job => job && job.timestamp < cutoff && job.data.is_scrape === true
    && job.data.mode === 'single_urls' && !job.data.crawl_id && !job.data.crawlId;
  try {
    if (process.argv.includes('--apply')) {
      const snapshot = JSON.parse(fs.readFileSync(0, 'utf8'));
      const result = {removed: 0, preserved: 0, errors: []};
      for (const saved of snapshot.jobs) {
        const job = await queue.getJob(saved.id);
        if (!eligible(job) || job.timestamp !== saved.timestamp) {
          result.preserved++;
          continue;
        }
        const state = await job.getState();
        if (!['waiting', 'prioritized', 'delayed', 'active', 'paused'].includes(state)) {
          result.preserved++;
          continue;
        }
        // 使用 BullMQ 自身的锁校验；不强制移除 active 锁，不直接 DEL Redis。
        try { await job.remove(); result.removed++; }
        catch (error) { result.errors.push({id: job.id, error: error.message}); }
      }
      process.stdout.write(JSON.stringify(result) + '\n');
    } else {
      const jobs = await queue.getJobs(['prioritized', 'wait', 'delayed', 'active', 'paused'], 0, -1);
      process.stdout.write(JSON.stringify({cutoff, jobs: jobs.filter(eligible).map(job => ({
        id: job.id, timestamp: job.timestamp, name: job.name, data: job.data, opts: job.opts,
      }))}) + '\n');
    }
  } finally {
    await queue.close();
    redisConnection.disconnect();
  }
}
main().catch(error => { process.stderr.write(error.message + '\n'); process.exitCode = 1; });
