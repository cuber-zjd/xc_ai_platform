import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { DatabaseZap, Plus, ServerCog } from 'lucide-react';

import { apiClient } from '@/api/client';
import { Button } from '@/components/ui/button';
import type { SapSystem } from '@/features/sap-assistant/types';

export default function SapSystemManagerPage() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    name: '',
    system_code: '',
    environment: 'dev',
    client: '800',
    language: 'ZH',
    ashost: '',
    sysnr: '00',
    user_env_key: '',
    password_env_key: '',
    is_production: false,
  });

  const { data = [] } = useQuery({
    queryKey: ['sap-systems'],
    queryFn: async () => apiClient.get('/sap/systems') as Promise<SapSystem[]>,
  });

  const createMutation = useMutation({
    mutationFn: async () => apiClient.post('/sap/systems', {
      ...form,
      max_rows: form.is_production ? 50 : 100,
      is_enabled: true,
      allow_web_search: false,
      allowed_tables: [],
      allowed_objects: ['Z*', 'Y*'],
    }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['sap-systems'] });
      setForm((value) => ({ ...value, name: '', system_code: '', ashost: '', user_env_key: '', password_env_key: '' }));
    },
  });

  const stats = useMemo(() => {
    const prod = data.filter((item) => item.is_production).length;
    return { total: data.length, prod };
  }, [data]);

  return (
    <div className="app-page p-6">
      <div className="grid gap-5 xl:grid-cols-[1fr_420px]">
        <section className="app-panel rounded-[32px] p-6">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="app-kicker">SAP 系统配置</div>
              <h1 className="mt-3 text-[30px] font-black tracking-[-0.04em] text-[#24233b]">RFC 连接和环境切换</h1>
              <p className="mt-2 text-sm text-[#7d8096]">推荐填写环境变量名；如果直接填写用户名和密码，后端会按明文连接使用。</p>
            </div>
            <div className="flex h-14 w-14 items-center justify-center rounded-[22px] bg-[#eef1ff] text-[#6e5df7]">
              <ServerCog className="h-6 w-6" />
            </div>
          </div>

          <div className="mt-6 grid gap-4 md:grid-cols-2">
            <Metric label="系统数量" value={stats.total} />
            <Metric label="生产系统" value={stats.prod} />
          </div>

          <div className="mt-6 space-y-3">
            {data.map((system) => (
              <div key={system.id} className="rounded-[26px] border border-white/80 bg-white/64 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <h3 className="text-base font-black text-[#29273f]">{system.name}</h3>
                    <p className="mt-1 text-sm text-[#7d8096]">
                      {system.system_code} / {system.client} / {system.environment}
                    </p>
                  </div>
                  <span className={`rounded-full px-3 py-1 text-xs font-bold ${system.is_production ? 'bg-amber-50 text-amber-700' : 'bg-emerald-50 text-emerald-700'}`}>
                    {system.is_production ? '生产受控' : '非生产'}
                  </span>
                </div>
                <div className="mt-3 grid gap-2 text-xs text-[#85889f] md:grid-cols-2">
                  <span>ASHOST：{system.ashost || '未配置'}</span>
                  <span>SYSNR：{system.sysnr || '未配置'}</span>
                  <span>用户/变量：{system.user_env_key || '未配置'}</span>
                  <span>密码/变量：{system.password_env_key || '未配置'}</span>
                </div>
              </div>
            ))}
          </div>
        </section>

        <aside className="app-panel rounded-[32px] p-6">
          <div className="flex items-center gap-3">
            <DatabaseZap className="h-5 w-5 text-[#6e5df7]" />
            <h2 className="text-lg font-black text-[#29273f]">新增系统</h2>
          </div>
          <div className="mt-5 space-y-3">
            <Input label="系统名称" value={form.name} onChange={(value) => setForm({ ...form, name: value })} placeholder="例如：集团生产 ECC" />
            <Input label="系统编码" value={form.system_code} onChange={(value) => setForm({ ...form, system_code: value })} placeholder="例如：PRD_800" />
            <div className="grid grid-cols-2 gap-3">
              <Select label="环境" value={form.environment} onChange={(value) => setForm({ ...form, environment: value })} options={['dev', 'qas', 'prd', 'sandbox']} />
              <Input label="客户端" value={form.client} onChange={(value) => setForm({ ...form, client: value })} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Input label="ASHOST" value={form.ashost} onChange={(value) => setForm({ ...form, ashost: value })} />
              <Input label="SYSNR" value={form.sysnr} onChange={(value) => setForm({ ...form, sysnr: value })} />
            </div>
            <Input label="用户或用户环境变量" value={form.user_env_key} onChange={(value) => setForm({ ...form, user_env_key: value })} placeholder="XCRFC 或 SAP_PRD_800_USER" />
            <Input label="密码或密码环境变量" value={form.password_env_key} onChange={(value) => setForm({ ...form, password_env_key: value })} placeholder="实际密码或 SAP_PRD_800_PASSWORD" type="password" />
            <label className="flex items-center gap-2 rounded-2xl bg-white/62 px-4 py-3 text-sm font-semibold text-[#55586e]">
              <input type="checkbox" checked={form.is_production} onChange={(event) => setForm({ ...form, is_production: event.target.checked })} />
              生产系统，启用更严格查询限制
            </label>
            <Button className="h-11 w-full rounded-2xl bg-[#6e5df7] text-white hover:bg-[#5d4ee0]" onClick={() => createMutation.mutate()} disabled={createMutation.isPending}>
              <Plus className="h-4 w-4" />
              保存系统
            </Button>
          </div>
        </aside>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-[24px] border border-white/80 bg-white/60 p-5">
      <div className="text-sm font-semibold text-[#85889f]">{label}</div>
      <div className="mt-3 text-3xl font-black text-[#29273f]">{value}</div>
    </div>
  );
}

function Input({ label, value, onChange, placeholder, type = 'text' }: { label: string; value: string; onChange: (value: string) => void; placeholder?: string; type?: string }) {
  return (
    <label className="block text-sm font-semibold text-[#55586e]">
      {label}
      <input type={type} className="mt-2 h-11 w-full rounded-2xl border border-white/80 bg-white/72 px-4 outline-none" value={value} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function Select({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: string[] }) {
  return (
    <label className="block text-sm font-semibold text-[#55586e]">
      {label}
      <select className="mt-2 h-11 w-full rounded-2xl border border-white/80 bg-white/72 px-4 outline-none" value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => <option key={option} value={option}>{option}</option>)}
      </select>
    </label>
  );
}
