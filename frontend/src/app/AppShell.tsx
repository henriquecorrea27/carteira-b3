import { NavLink, Outlet } from "react-router-dom";
import { Eye, EyeOff, Monitor, Moon, RefreshCw, Sun } from "lucide-react";
import { toast } from "sonner";
import { useRefreshPrices, useSummary } from "@/api/hooks";
import { USE_MOCKS } from "@/api/endpoints";
import { ReportDialog } from "@/features/relatorio/ReportDialog";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/menu";
import { formatDateTimeShort } from "@/lib/format";
import { cn } from "@/lib/utils";
import { usePrivacy } from "./privacy";
import { useTheme, type ThemePreference } from "./theme";

const TABS = [
  { to: "/carteira", label: "Carteira" },
  { to: "/proventos", label: "Proventos" },
  { to: "/operacoes", label: "Operações" },
  { to: "/analise", label: "Análise" },
  { to: "/observacao", label: "Observação" },
  { to: "/importar", label: "Importar" },
];

function Wordmark() {
  return (
    <NavLink to="/carteira" className="flex items-center gap-2 rounded-md pr-1" aria-label="Carteira B3 — início">
      <svg viewBox="0 0 32 32" className="size-7" aria-hidden>
        <rect width="32" height="32" rx="8" fill="var(--ink)" />
        <rect x="7" y="17" width="4" height="8" rx="1" fill="var(--paper)" />
        <rect x="14" y="12" width="4" height="13" rx="1" fill="var(--paper)" />
        <rect x="21" y="7" width="4" height="18" rx="1" fill="var(--up)" />
      </svg>
      <span className="text-lg font-semibold tracking-tight">Carteira B3</span>
    </NavLink>
  );
}

function ThemeMenu() {
  const { preference, resolved, setPreference } = useTheme();
  const Icon = resolved === "dark" ? Moon : Sun;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Tema">
          <Icon />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuRadioGroup value={preference} onValueChange={(v) => setPreference(v as ThemePreference)}>
          <DropdownMenuRadioItem value="light">
            <Sun /> Claro
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="dark">
            <Moon /> Escuro
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="system">
            <Monitor /> Seguir o sistema
          </DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function PrivacyToggle() {
  const [hidden, setHidden] = usePrivacy();
  const label = hidden ? "Mostrar valores" : "Ocultar valores";
  return (
    <Button variant="ghost" size="icon" aria-label={label} title={label} aria-pressed={hidden} onClick={() => setHidden(!hidden)}>
      {hidden ? <EyeOff /> : <Eye />}
    </Button>
  );
}

function RefreshPrices() {
  const summary = useSummary();
  const refresh = useRefreshPrices();
  const onClick = () =>
    refresh.mutate(undefined, {
      onSuccess: (r) =>
        r.failed
          ? toast.warning(`Preços atualizados para ${r.updated} ativos. ${r.failed} falharam e mantêm a última cotação.`)
          : toast.success(`Preços atualizados para ${r.updated} ativos.`),
      onError: (e) => toast.error(e.message),
    });
  return (
    <div className="flex items-center gap-3">
      {summary.data?.prices_as_of && (
        <span className="hidden text-sm text-muted lg:inline">
          Cotações de {formatDateTimeShort(summary.data.prices_as_of)}
        </span>
      )}
      <Button size="sm" onClick={onClick} disabled={refresh.isPending}>
        <RefreshCw className={cn(refresh.isPending && "animate-spin")} />
        <span className="hidden sm:inline">{refresh.isPending ? "Atualizando…" : "Atualizar preços"}</span>
      </Button>
    </div>
  );
}

export function AppShell() {
  return (
    <div className="min-h-dvh">
      <a
        href="#conteudo"
        className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-ink focus:px-3 focus:py-2 focus:text-paper"
      >
        Pular para o conteúdo
      </a>
      <header className="sticky top-0 z-40 border-b border-line bg-surface/90 backdrop-blur supports-[backdrop-filter]:bg-surface/80">
        <div className="mx-auto flex max-w-[1240px] flex-wrap items-center gap-x-6 px-4 sm:px-6">
          <div className="flex h-14 items-center">
            <Wordmark />
          </div>
          <nav aria-label="Seções" className="order-3 -mx-4 w-[calc(100%+2rem)] overflow-x-auto overflow-y-hidden px-4 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden md:order-none md:mx-0 md:w-auto md:overflow-visible md:px-0">
            <ul className="flex h-11 items-stretch gap-1 md:h-14">
              {TABS.map((tab) => (
                <li key={tab.to} className="flex">
                  <NavLink
                    to={tab.to}
                    className={({ isActive }) =>
                      cn(
                        "relative flex items-center px-2.5 text-base font-medium text-ink-2 transition-colors hover:text-ink",
                        "after:absolute after:inset-x-2.5 after:-bottom-px after:h-0.5 after:rounded-full after:bg-transparent",
                        isActive && "text-ink after:bg-ink",
                      )
                    }
                  >
                    {tab.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
          <div className="ml-auto flex h-14 items-center gap-1.5">
            {USE_MOCKS && (
              <span className="hidden rounded-sm border border-dashed border-line-strong px-1.5 py-0.5 text-xs text-muted xl:inline" title="Os dados exibidos são fictícios até o backend ficar pronto.">
                Dados de demonstração
              </span>
            )}
            <RefreshPrices />
            <PrivacyToggle />
            <ReportDialog />
            <ThemeMenu />
          </div>
        </div>
      </header>
      <main id="conteudo" className="mx-auto max-w-[1240px] px-4 pb-16 pt-6 sm:px-6">
        <Outlet />
      </main>
    </div>
  );
}
