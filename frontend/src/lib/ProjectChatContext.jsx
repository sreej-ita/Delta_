import { createContext, useContext, useState } from "react";

const ProjectChatContext = createContext(null);

/**
 * Wraps the app so any page can publish "here's the project currently on
 * screen" and the floating Chatbot (mounted once, outside the routed pages)
 * can read it and ground its answers in that project's real metrics.
 */
export function ProjectChatProvider({ children }) {
  const [context, setContext] = useState(null);
  return (
    <ProjectChatContext.Provider value={{ context, setContext }}>
      {children}
    </ProjectChatContext.Provider>
  );
}

/** Read the current project's context — used by Chatbot.jsx. */
export function useProjectChatContext() {
  const ctx = useContext(ProjectChatContext);
  return ctx?.context ?? null;
}

/**
 * Call from a project page (e.g. ProjectDetail.jsx) whenever its analyze()
 * result changes, so the chatbot stays grounded in what's currently on
 * screen. Pass null to clear it (e.g. while a new analysis is loading, or
 * on unmount) so the assistant doesn't answer using stale/wrong data.
 *
 * Typical usage inside ProjectDetail.jsx:
 *
 *   import { useSetProjectChatContext } from "../lib/ProjectChatContext.jsx";
 *   import { buildChatProjectContext } from "../lib/api.js";
 *   ...
 *   const setProjectChatContext = useSetProjectChatContext();
 *   useEffect(() => {
 *     setProjectChatContext(result ? buildChatProjectContext(result) : null);
 *     return () => setProjectChatContext(null);
 *   }, [result]);
 */
export function useSetProjectChatContext() {
  const ctx = useContext(ProjectChatContext);
  return ctx?.setContext ?? (() => {});
}