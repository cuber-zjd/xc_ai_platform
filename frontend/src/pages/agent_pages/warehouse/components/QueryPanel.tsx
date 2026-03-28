import { useState, useRef, useCallback } from "react";
import { Mic, MicOff, Send, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { MaterialItem } from "../types";

interface Props {
  onQuery: (query: string) => void;
  isQuerying: boolean;
  results: MaterialItem[];
  selectedMaterials: Set<number>;
  onMaterialToggle: (id: number) => void;
  onClearSelection: () => void;
}

export default function QueryPanel({
  onQuery,
  isQuerying,
  results,
  selectedMaterials,
  onMaterialToggle,
  onClearSelection,
}: Props) {
  const [inputValue, setInputValue] = useState("");
  const [isListening, setIsListening] = useState(false);
  const recognitionRef = useRef<SpeechRecognition | null>(null);

  const handleSubmit = () => {
    if (!inputValue.trim() || isQuerying) return;
    onQuery(inputValue);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleSubmit();
    }
  };

  const startListening = useCallback(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert("您的浏览器不支持语音识别功能");
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = "zh-CN";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      setIsListening(true);
    };

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      const transcript = event.results[0][0].transcript;
      setInputValue(transcript);
      onQuery(transcript);
    };

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      console.error("语音识别错误:", event.error);
      setIsListening(false);
    };

    recognition.onend = () => {
      setIsListening(false);
    };

    recognition.start();
    recognitionRef.current = recognition;
  }, [onQuery]);

  const stopListening = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      recognitionRef.current = null;
    }
    setIsListening(false);
  }, []);

  return (
    <div className="flex flex-col h-full bg-white/90 backdrop-blur-xl rounded-2xl shadow-lg border border-zinc-200/50 overflow-hidden">
      <div className="p-5 border-b border-zinc-200/50">
        <h3 className="text-lg font-semibold text-[#2C3E50]">仓储查询</h3>
        <p className="text-sm text-[#6B7280]">语音或文字查询物料位置</p>
      </div>

      <div className="p-4 space-y-4">
        <div className="flex gap-2">
          <div className="flex-1 relative">
            <Input
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="请输入文字进行查询位置"
              disabled={isQuerying}
              className="pr-10 border-[#D1D5DB] rounded-xl focus:border-[#3B82F6] focus:ring-[#3B82F6]/20 text-[#2C3E50] placeholder:text-[#9CA3AF]"
            />
            <Button
              size="icon"
              variant="ghost"
              className="absolute right-1 top-1/2 -translate-y-1/2 h-8 w-8"
              onClick={isListening ? stopListening : startListening}
              disabled={isQuerying}
            >
              {isListening ? (
                <MicOff className="h-4 w-4 text-red-500 animate-pulse" />
              ) : (
                <Mic className="h-4 w-4" />
              )}
            </Button>
          </div>
          <Button 
            onClick={handleSubmit} 
            disabled={!inputValue.trim() || isQuerying}
            className="bg-[#2C3E50] hover:bg-[#34495E] text-white rounded-xl px-4"
          >
            {isQuerying ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </Button>
        </div>

        {isListening && (
          <div className="text-sm text-red-500 flex items-center gap-2">
            <Mic className="h-4 w-4 animate-pulse" />
            正在聆听...
          </div>
        )}
      </div>

      <div className="flex-1 overflow-auto p-4">
        {results.length > 0 ? (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm text-[#6B7280]">找到 {results.length} 个物料</span>
              {selectedMaterials.size > 0 && (
                <Button 
                  variant="outline" 
                  size="sm" 
                  onClick={onClearSelection}
                  className="border-[#D1D5DB] text-[#34495E] hover:bg-zinc-50 rounded-lg"
                >
                  删除选择 ({selectedMaterials.size})
                </Button>
              )}
            </div>
            <div className="space-y-2">
              {results.map((item) => (
                <div
                  key={item.id}
                  className={`p-3 rounded-xl border cursor-pointer transition-all ${
                    selectedMaterials.has(item.id)
                      ? "border-[#3B82F6] bg-[#EFF6FF]"
                      : "border-[#E5E7EB] hover:border-[#D1D5DB] bg-white"
                  }`}
                  onClick={() => onMaterialToggle(item.id)}
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="font-medium text-[#2C3E50]">{item.material_code}</div>
                      <div className="text-sm text-[#6B7280]">{item.material_desc || "无描述"}</div>
                      <div className="text-xs text-[#9CA3AF] mt-1">
                        安全帽_橙色、红色 | 7 EA
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-sm font-medium text-[#2C3E50]">
                        {item.unrestricted_qty} {item.base_uom}
                      </div>
                      <div className="text-xs text-[#6B7280]">{item.storage_bin}</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-[#9CA3AF]">
            <Mic className="h-12 w-12 mb-2 opacity-50" />
            <p className="text-sm">语音输入或文字搜索物料</p>
          </div>
        )}
      </div>
    </div>
  );
}

declare global {
  interface Window {
    SpeechRecognition: new () => SpeechRecognition;
    webkitSpeechRecognition: new () => SpeechRecognition;
  }
}

interface SpeechRecognition extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  onstart: ((this: SpeechRecognition, ev: Event) => void) | null;
  onresult: ((this: SpeechRecognition, ev: SpeechRecognitionEvent) => void) | null;
  onerror: ((this: SpeechRecognition, ev: SpeechRecognitionErrorEvent) => void) | null;
  onend: ((this: SpeechRecognition, ev: Event) => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}

interface SpeechRecognitionEvent extends Event {
  results: SpeechRecognitionResultList;
  resultIndex: number;
}

interface SpeechRecognitionErrorEvent extends Event {
  error: string;
}

interface SpeechRecognitionResultList {
  length: number;
  item(index: number): SpeechRecognitionResult;
  [index: number]: SpeechRecognitionResult;
}

interface SpeechRecognitionResult {
  length: number;
  item(index: number): SpeechRecognitionAlternative;
  [index: number]: SpeechRecognitionAlternative;
  isFinal: boolean;
}

interface SpeechRecognitionAlternative {
  transcript: string;
  confidence: number;
}
