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


export function useSetProjectChatContext() {
  const ctx = useContext(ProjectChatContext);
  return ctx?.setContext ?? (() => {});
}
