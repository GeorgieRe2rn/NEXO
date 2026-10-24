import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import { FeedProvider } from "./components/FeedContext";
const MatchDetail = lazy(() => import("./pages/MatchDetail"));
const Squads = lazy(() => import("./pages/Squads"));
const TeamPage = lazy(() => import("./pages/TeamPage"));
const AdminLogin = lazy(() => import("./pages/AdminLogin"));
const AdminHome = lazy(() => import("./pages/AdminHome"));
const EventCatalog = lazy(() => import("./pages/EventCatalog"));
const MyForecasts = lazy(() => import("./pages/MyForecasts"));
const Standings = lazy(() => import("./pages/Standings"));

export default function App() {
  return (
    <FeedProvider>
      <Layout>
        <Suspense
          fallback={
            <div
              className="skeleton h-64"
              role="status"
              aria-label="Cargando página"
            />
          }
        >
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/en-vivo" element={<Dashboard />} />
            <Route path="/cartelera" element={<EventCatalog />} />
            <Route path="/mis-pronosticos" element={<MyForecasts />} />
            <Route path="/metodologia" element={<Navigate to="/admin?modulo=modelo" replace />} />
            <Route path="/match/:id" element={<MatchDetail />} />
            <Route path="/plantillas" element={<Squads />} />
            <Route path="/posiciones" element={<Standings />} />
            <Route path="/equipo/:id" element={<TeamPage />} />
            <Route path="/admin/login" element={<AdminLogin />} />
            <Route path="/admin" element={<AdminHome />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </Layout>
    </FeedProvider>
  );
}
