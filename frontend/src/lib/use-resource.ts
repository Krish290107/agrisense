"use client";
import {useCallback, useEffect, useState} from "react";
export function useResource<T>(load: (signal: AbortSignal) => Promise<T>) {
  const [state,setState] = useState<{loading: boolean; data?: T; error?: string}>({loading: true});
  const [attempt,setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal).then(data => {if (!controller.signal.aborted) setState({loading: false,data});})
      .catch((error: unknown) => {if (!controller.signal.aborted) setState({loading: false,error: error instanceof Error ? error.message : "Could not load data. Please retry."});});
    return () => controller.abort();
  }, [load,attempt]);
  const reload = useCallback(() => {setState({loading: true}); setAttempt(n => n+1);}, []);
  return {...state,reload};
}
