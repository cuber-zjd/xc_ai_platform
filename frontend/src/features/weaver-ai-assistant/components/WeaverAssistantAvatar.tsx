import { motion } from "framer-motion";

interface WeaverAssistantAvatarProps {
  className?: string;
  mode?: "idle" | "thinking" | "review" | "success";
  title?: string;
  glow?: boolean;
}

const MASCOT_URL = "/ai/weaver-assistant/mascot-selected.png";

export function WeaverAssistantAvatar({
  className,
  mode = "idle",
  title = "泛微流程 AI 助手",
  glow = false,
}: WeaverAssistantAvatarProps) {
  const active = mode === "thinking" || mode === "review";
  const success = mode === "success";

  return (
    <motion.span
      role="img"
      aria-label={title}
      className={`relative inline-flex shrink-0 items-center justify-center ${className || ""}`}
      initial={false}
      animate={
        active
          ? { y: [0, -5, 0], rotate: [0, -2, 2, 0], scale: [1, 1.035, 1] }
          : success
            ? { y: [0, -6, 0], scale: [1, 1.07, 1] }
            : { y: [0, -4, 0], rotate: [0, -1.5, 0, 1.5, 0] }
      }
      whileHover={{ y: -5, scale: 1.06, rotate: 2 }}
      transition={{ duration: active ? 1.45 : success ? 1.8 : 3.2, repeat: Infinity, ease: "easeInOut" }}
    >
      <span className="relative inline-flex h-full max-w-full aspect-square items-center justify-center">
        <img
          src={MASCOT_URL}
          alt=""
          draggable={false}
          className={`relative z-10 h-full w-full select-none object-contain ${
            glow ? "drop-shadow-[0_0_10px_rgba(96,165,250,0.65)]" : ""
          }`}
        />
        <BlinkEye side="left" active={active} />
        <BlinkEye side="right" active={active} />
      </span>
    </motion.span>
  );
}

function BlinkEye({ side, active }: { side: "left" | "right"; active: boolean }) {
  return (
    <motion.span
      aria-hidden="true"
      className="absolute z-20 h-[7.4%] w-[15.2%] overflow-hidden rounded-full bg-[#061945]"
      style={{
        left: side === "left" ? "28.5%" : "56.3%",
        top: "54.1%",
        transformOrigin: "center",
      }}
      animate={{ scaleY: [0, 0, 1, 1, 0, 0] }}
      transition={{
        duration: active ? 2.3 : 4.6,
        repeat: Infinity,
        ease: "easeInOut",
        times: [0, 0.72, 0.76, 0.8, 0.84, 1],
      }}
    >
      <span className="absolute left-[14%] right-[14%] top-1/2 h-[2px] -translate-y-1/2 rounded-full bg-cyan-300 shadow-[0_0_5px_rgba(34,211,238,0.95)]" />
    </motion.span>
  );
}
