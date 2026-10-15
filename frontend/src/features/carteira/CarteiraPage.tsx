import { Link, useNavigate, useParams } from "react-router-dom";
import { FileUp, PenLine, WalletMinimal } from "lucide-react";
import { usePending, useSummary } from "@/api/hooks";
import type { PortfolioSummary } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Segmented } from "@/components/ui/segmented";
import { EmptyState, Panel, Skeleton } from "@/components/ui/misc";
import { Delta } from "@/components/domain";
import { formatBRL, toNumber } from "@/lib/format";
import { PendingBanner, QueryError, SourceWarnings } from "../shared";
import { ResumoView } from "./ResumoView";
import { PosicoesView } from "./PosicoesView";
import { RentabilidadeView } from "./RentabilidadeView";

type View = "resumo" | "posicoes" | "rentabilidade";

const VIEWS: { value: View; label: string }[] = [
  { value: "resumo", label: "Resumo" },
  { value: "posicoes", label: "Posições" },
  { value: "rentabilidade", label: "Rentabilidade" },
];

/** A portfolio without any operation yet (e.g. a profile just created). */
function isEmpty(s: PortfolioSummary): boolean {
  return [s.equity, s.invested, s.realized_pnl, s.dividends_total].every((v) => toNumber(v) === 0);
}

function EmptyPortfolio() {
  return (
    <Panel>
      <EmptyState
        icon={WalletMinimal}
        title="Esta carteira ainda não tem operações"
        action={
          <div className="flex flex-wrap justify-center gap-2">
            <Button asChild variant="primary">
              <Link to="/importar">
                <FileUp /> Importar extratos da B3
              </Link>
            </Button>
            <Button asChild>
              <Link to="/operacoes">
                <PenLine /> Lançar operações
              </Link>
            </Button>
          </div>
        }
      >
        Importe os extratos de Negociação e Movimentação da Área do Investidor da B3, ou lance as compras e vendas à mão.
        Proventos e eventos entram sozinhos depois.
      </EmptyState>
    </Panel>
  );
}

export function CarteiraPage() {
  const params = useParams();
  const navigate = useNavigate();
  const view: View = VIEWS.some((v) => v.value === params.view) ? (params.view as View) : "resumo";
  const summary = useSummary();
  const pending = usePending();

  return (
    <>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-x-8 gap-y-4">
        <div>
          <p className="text-ink-2">Patrimônio</p>
          {summary.isPending ? (
            <Skeleton className="mt-2 h-12 w-72" />
          ) : summary.data ? (
            <>
              <p className="mt-1 text-hero font-semibold tracking-[-0.035em]">
                <span className="mr-1.5 align-[0.42em] text-xl font-medium tracking-normal text-ink-2">R$</span>
                <span className="sensitive">{formatBRL(summary.data.equity).replace(/^R\$\s/, "")}</span>
              </p>
              <p className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-ink-2">
                <span className="inline-flex items-center gap-1.5">
                  <Delta value={summary.data.day_change} kind="brl" arrow={false} />
                  <Delta value={summary.data.day_change_pct} className="text-sm" />
                  <span>hoje</span>
                </span>
                <span aria-hidden className="hidden h-3 w-px bg-line-strong sm:block" />
                <span className="inline-flex items-center gap-1.5">
                  <Delta value={summary.data.total_return_pct} />
                  <span>desde a primeira compra</span>
                </span>
              </p>
            </>
          ) : null}
        </div>
        <Segmented
          aria-label="Visão da carteira"
          value={view}
          onChange={(v) => navigate(v === "resumo" ? "/carteira" : `/carteira/${v}`)}
          options={VIEWS}
        />
      </div>

      {summary.isError && <QueryError what="o resumo da carteira" error={summary.error} onRetry={() => summary.refetch()} />}
      <SourceWarnings warnings={summary.data?.warnings} />
      <PendingBanner items={pending.data} />

      {summary.data && isEmpty(summary.data) ? (
        <EmptyPortfolio />
      ) : (
        <>
          {view === "resumo" && <ResumoView />}
          {view === "posicoes" && <PosicoesView />}
          {view === "rentabilidade" && <RentabilidadeView />}
        </>
      )}
    </>
  );
}
