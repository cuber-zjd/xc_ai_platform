import { useState, useRef } from 'react';
import { cn } from '@/lib/utils';
import { Send } from 'lucide-react';

export default function ChatHomePage() {
    const [inputValue, setInputValue] = useState('');
    const inputRef = useRef<HTMLInputElement>(null);

    const handleSubmit = () => {
        if (!inputValue.trim()) return;
        console.log('发送消息:', inputValue);
        setInputValue('');
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            handleSubmit();
        }
    };

    return (
        <div className="flex-1 flex flex-col items-center justify-center h-full w-full relative">
            {/* The Glass Container from the user's reference image */}
            <div className="w-full max-w-4xl aspect-[1.8/1] bg-white/50 backdrop-blur-[32px] border border-white/80 rounded-[2.5rem] shadow-[0_8px_40px_rgba(0,0,0,0.03),inset_0_1px_1px_rgba(255,255,255,1)] flex flex-col relative overflow-hidden ring-1 ring-black/[0.02]">
                
                {/* Inner highlight overlay for extra glassy light-refracting effect */}
                <div className="absolute inset-0 bg-gradient-to-br from-white/60 via-transparent to-white/20 pointer-events-none" />

                <div className="flex-1 flex items-center justify-center pb-12 relative z-10">
                    <h1 className="text-4xl md:text-[3.5rem] font-medium tracking-tight text-neutral-800 drop-shadow-sm">
                        The Nexus Chat.
                    </h1>
                </div>

                {/* Input Area */}
                <div className="absolute bottom-8 left-1/2 -translate-x-1/2 w-[85%] max-w-2xl z-20">
                    <div className="bg-white/80 backdrop-blur-2xl border border-white/90 rounded-full p-1.5 flex items-center shadow-[0_4px_20px_rgba(0,0,0,0.05),inset_0_2px_4px_rgba(255,255,255,1)] transition-all focus-within:shadow-[0_8px_30px_rgba(0,0,0,0.08),inset_0_2px_4px_rgba(255,255,255,1)] ring-1 ring-black/[0.03]">
                        <input
                            ref={inputRef}
                            type="text"
                            value={inputValue}
                            onChange={(e) => setInputValue(e.target.value)}
                            onKeyDown={handleKeyDown}
                            placeholder="Type your message..."
                            className="flex-1 bg-transparent border-none outline-none px-6 text-[15px] placeholder:text-neutral-400 text-neutral-800 h-11 font-medium"
                        />
                        <button 
                            onClick={handleSubmit}
                            className={cn(
                                "p-3 rounded-full transition-all duration-300 shrink-0 flex items-center justify-center",
                                inputValue.trim() 
                                    ? "bg-neutral-800 text-white shadow-lg hover:bg-black hover:scale-105" 
                                    : "bg-transparent text-neutral-400 hover:text-neutral-600 hover:bg-black/5"
                            )}
                        >
                            <Send className="h-5 w-5 ml-0.5" />
                        </button>
                    </div>
                </div>
            </div>
            
            {/* Bottom decorative subtle glow to anchor the chat card */}
            <div className="absolute top-[80%] left-1/2 -translate-x-1/2 w-3/4 h-32 bg-white/40 blur-[60px] pointer-events-none z-0" />
        </div>
    );
}
