import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import Landing from "./pages/Landing.jsx";
import ProjectDetail from "./pages/ProjectDetail.jsx";
import Chatbot from "./components/Chatbot.jsx";
import { ProjectChatProvider } from "./lib/ProjectChatContext.jsx";

export default function App() {
  const location = useLocation();

  return (
    <ProjectChatProvider>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/projects/:projectId" element={<ProjectDetail />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      {location.pathname !== "/" && <Chatbot />}
    </ProjectChatProvider>
  );
}
