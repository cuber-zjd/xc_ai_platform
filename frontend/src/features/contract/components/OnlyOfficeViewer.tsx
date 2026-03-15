import { useEffect, useRef, useState } from "react";
import type { ContractAuditLog } from "../types";
import type { EditorConfig } from "../hooks/useContract";
import { Loader2, AlertCircle } from "lucide-react";

interface Props {
    editorConfig?: EditorConfig;
    className?: string;
    highlightLog?: ContractAuditLog | null;
    onDocumentReady?: () => void;
}

export function OnlyOfficeViewer({
    editorConfig,
    className,
    highlightLog,
    onDocumentReady,
}: Props) {
    const wrapperRef = useRef<HTMLDivElement>(null);
    const editorRef = useRef<any>(null);
    const editorContainerId = useRef<string>(`onlyoffice-editor-${Date.now()}`);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [isScriptLoaded, setIsScriptLoaded] = useState(false);

    // 加载 OnlyOffice 脚本
    useEffect(() => {
        if (!editorConfig) return;

        // 检查是否已经加载
        if ((window as any).DocsAPI) {
            setIsScriptLoaded(true);
            return;
        }

        const script = document.createElement("script");
        script.src = editorConfig.api_url;
        script.async = true;
        script.onload = () => {
            setIsScriptLoaded(true);
        };
        script.onerror = () => {
            setError("无法加载 OnlyOffice API 脚本");
            setIsLoading(false);
        };
        document.head.appendChild(script);

        return () => {
            // 不移除脚本，因为可能其他地方还在用
        };
    }, [editorConfig?.api_url]);

    // 初始化编辑器
    useEffect(() => {
        if (!isScriptLoaded || !editorConfig || !wrapperRef.current) return;

        const DocsAPI = (window as any).DocsAPI;
        if (!DocsAPI) {
            setError("DocsAPI 未加载");
            setIsLoading(false);
            return;
        }

        // 清理旧编辑器
        if (editorRef.current) {
            try {
                editorRef.current.destroyEditor();
            } catch (e) {
                console.warn("Editor cleanup error:", e);
            }
            editorRef.current = null;
        }

        // 清空容器并创建新的编辑器 div
        const wrapper = wrapperRef.current;
        wrapper.innerHTML = "";

        const editorDiv = document.createElement("div");
        editorDiv.id = editorContainerId.current;
        editorDiv.style.width = "100%";
        editorDiv.style.height = "100%";
        wrapper.appendChild(editorDiv);

        // 配置编辑器
        const config = {
            ...editorConfig.config,
            events: {
                onDocumentReady: () => {
                    setIsLoading(false);
                    onDocumentReady?.();
                },
                onError: (event: any) => {
                    console.error("OnlyOffice Error:", event);
                    setError(`文档加载失败: ${event.data?.errorDescription || "未知错误"}`);
                    setIsLoading(false);
                },
            },
        };

        try {
            setIsLoading(true);
            setError(null);
            editorRef.current = new DocsAPI.DocEditor(editorContainerId.current, config);
        } catch (err: any) {
            console.error("Failed to init OnlyOffice:", err);
            setError(err.message || "初始化编辑器失败");
            setIsLoading(false);
        }

        return () => {
            if (editorRef.current) {
                try {
                    editorRef.current.destroyEditor();
                } catch (e) {
                    console.warn("Editor cleanup error:", e);
                }
                editorRef.current = null;
            }
            // 清空容器，避免 React 冲突
            if (wrapper) {
                wrapper.innerHTML = "";
            }
        };
    }, [isScriptLoaded, editorConfig, onDocumentReady]);

    // 高亮文本功能 - 尝试多种方案触发 OnlyOffice 搜索
    useEffect(() => {
        if (!highlightLog || !editorRef.current) return;

        const searchText = highlightLog.quote_text;
        if (!searchText) {
            console.warn("No quote_text to search for");
            return;
        }

        console.log("Attempting to search for:", searchText.substring(0, 50));

        // 方案1: 尝试使用 executeMethod 调用搜索
        try {
            if (typeof editorRef.current.executeMethod === 'function') {
                // 打开搜索替换面板并填入搜索文本
                editorRef.current.executeMethod('StartFindAndReplace', [searchText, ''], (result: any) => {
                    console.log("executeMethod StartFindAndReplace result:", result);
                });
                return;
            }
        } catch (e) {
            console.log("executeMethod not available:", e);
        }


        // 方案2: 通过 PostMessage 发送搜索命令到 iframe
        try {
            const iframe = document.querySelector('iframe[name*="frameEditor"]') as HTMLIFrameElement;
            if (iframe && iframe.contentWindow) {
                // 聚焦 iframe
                iframe.contentWindow.focus();

                // 尝试发送搜索消息
                iframe.contentWindow.postMessage({
                    type: 'search',
                    data: { text: searchText }
                }, '*');

                console.log("Posted search message to iframe");
            }
        } catch (e) {
            console.log("PostMessage failed:", e);
        }

        // 方案3: 模拟 Ctrl+F 键盘事件
        try {
            const iframe = document.querySelector('iframe[name*="frameEditor"]') as HTMLIFrameElement;
            if (iframe && iframe.contentWindow) {
                iframe.contentWindow.focus();

                // 创建并分发 Ctrl+F 事件
                const event = new KeyboardEvent('keydown', {
                    key: 'f',
                    code: 'KeyF',
                    ctrlKey: true,
                    bubbles: true,
                    cancelable: true
                });
                iframe.contentDocument?.dispatchEvent(event);

                // 短暂延迟后尝试填入搜索文本
                setTimeout(() => {
                    // 尝试找到搜索输入框并填入文本
                    const searchInput = iframe.contentDocument?.querySelector('input[type="text"]') as HTMLInputElement;
                    if (searchInput) {
                        searchInput.value = searchText;
                        searchInput.dispatchEvent(new Event('input', { bubbles: true }));
                        console.log("Search text filled in input");
                    }
                }, 300);
            }
        } catch (e) {
            console.log("Keyboard simulation failed:", e);
        }

    }, [highlightLog]);

    if (!editorConfig) {
        return (
            <div className={`flex items-center justify-center bg-muted/10 border ${className}`}>
                <div className="text-center text-muted-foreground">
                    <Loader2 className="h-8 w-8 animate-spin mx-auto mb-2" />
                    <p>正在获取文档配置...</p>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className={`flex items-center justify-center bg-red-50 border border-red-200 ${className}`}>
                <div className="text-center text-red-600 p-8">
                    <AlertCircle className="h-12 w-12 mx-auto mb-4" />
                    <p className="font-medium mb-2">文档预览失败</p>
                    <p className="text-sm text-red-500 mb-4">{error}</p>
                    <p className="text-xs text-gray-500">
                        请确保 OnlyOffice Document Server 正在运行 ({editorConfig.server_url})
                    </p>
                    <a
                        href={editorConfig.config.document.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-block mt-4 px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 text-sm"
                    >
                        直接下载文档
                    </a>
                </div>
            </div>
        );
    }

    return (
        <div className={`relative ${className}`}>
            {isLoading && (
                <div className="absolute inset-0 flex items-center justify-center bg-white/80 z-10">
                    <div className="text-center text-muted-foreground">
                        <Loader2 className="h-8 w-8 animate-spin mx-auto mb-2" />
                        <p>正在加载文档预览...</p>
                    </div>
                </div>
            )}
            {/* 使用 ref 直接控制这个 div，不让 React 管理其内容 */}
            <div
                ref={wrapperRef}
                className="w-full h-full min-h-[600px]"
            />
        </div>
    );
}
