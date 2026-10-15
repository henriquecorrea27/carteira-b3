import { Suspense, lazy } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";
import { useProfileId } from "@/api/profile";
import { TooltipProvider } from "@/components/ui/menu";
import { Skeleton } from "@/components/ui/misc";
import { AppShell } from "./AppShell";
import { useTheme } from "./theme";

// One chunk per tab: charts (Recharts, lightweight-charts) load only where they are used.
const CarteiraPage = lazy(() => import("@/features/carteira/CarteiraPage").then((m) => ({ default: m.CarteiraPage })));
const ProventosPage = lazy(() => import("@/features/proventos/ProventosPage").then((m) => ({ default: m.ProventosPage })));
const OperacoesPage = lazy(() => import("@/features/operacoes/OperacoesPage").then((m) => ({ default: m.OperacoesPage })));
const AnalisePage = lazy(() => import("@/features/analise/AnalisePage").then((m) => ({ default: m.AnalisePage })));
const ObservacaoPage = lazy(() => import("@/features/observacao/ObservacaoPage").then((m) => ({ default: m.ObservacaoPage })));
const ImportarPage = lazy(() => import("@/features/importar/ImportarPage").then((m) => ({ default: m.ImportarPage })));

function PageFallback() {
  return (
    <div className="flex flex-col gap-4" aria-busy="true">
      <Skeleton className="h-10 w-64" />
      <Skeleton className="h-80 w-full" />
    </div>
  );
}

export function App() {
  const { resolved } = useTheme();
  const profile = useProfileId();
  return (
    <TooltipProvider delayDuration={250}>
      <Suspense fallback={null}>
        {/* Keyed by the profile: switching portfolios remounts everything, no state carries over */}
        <Routes key={profile ?? ""}>
          <Route element={<AppShell />}>
            <Route index element={<Navigate to="/carteira" replace />} />
            <Route path="carteira/:view?" element={<Suspense fallback={<PageFallback />}><CarteiraPage /></Suspense>} />
            <Route path="proventos" element={<Suspense fallback={<PageFallback />}><ProventosPage /></Suspense>} />
            <Route path="operacoes" element={<Suspense fallback={<PageFallback />}><OperacoesPage /></Suspense>} />
            <Route path="analise/:ticker?" element={<Suspense fallback={<PageFallback />}><AnalisePage /></Suspense>} />
            <Route path="observacao" element={<Suspense fallback={<PageFallback />}><ObservacaoPage /></Suspense>} />
            <Route path="importar" element={<Suspense fallback={<PageFallback />}><ImportarPage /></Suspense>} />
            <Route path="*" element={<Navigate to="/carteira" replace />} />
          </Route>
        </Routes>
      </Suspense>
      <Toaster
        theme={resolved}
        position="bottom-right"
        toastOptions={{
          classNames: {
            toast: "!rounded-lg !border !border-line !bg-surface !text-ink !font-sans !shadow-[0_12px_32px_-12px_rgb(0_0_0/0.3)]",
            description: "!text-ink-2",
          },
        }}
      />
    </TooltipProvider>
  );
}
