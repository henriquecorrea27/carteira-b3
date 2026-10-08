import * as React from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, FileSpreadsheet, Upload } from "lucide-react";
import { toast } from "sonner";
import { useImportCommit, useImportPreview } from "@/api/hooks";
import type { ImportPreview, ImportResult, ImportRowStatus } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Panel, PanelHeader } from "@/components/ui/misc";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { formatBRL, formatDate, formatQuantity } from "@/lib/format";
import { IMPORT_STATUS_LABEL, TX_TYPE_LABEL } from "@/lib/labels";
import { cn } from "@/lib/utils";
import { PageTitle } from "../shared";

const STATUS_TONE: Record<ImportRowStatus, "up" | "neutral" | "outline" | "down"> = {
  NEW: "up",
  DUPLICATE: "neutral",
  IGNORED: "outline",
  ERROR: "down",
};

const STEPS = ["Escolher arquivo", "Revisar a prévia", "Concluído"];

function Steps({ current }: { current: number }) {
  return (
    <ol className="mb-6 flex flex-wrap items-center gap-x-2 gap-y-2 text-sm">
      {STEPS.map((s, i) => (
        <li key={s} className="flex items-center gap-2">
          <span
            className={cn(
              "num flex size-6 items-center justify-center rounded-full border text-xs font-semibold",
              i < current && "border-ink bg-ink text-paper",
              i === current && "border-ink text-ink",
              i > current && "border-line-strong text-muted",
            )}
          >
            {i + 1}
          </span>
          <span className={cn(i === current ? "font-medium text-ink" : "text-ink-2")}>{s}</span>
          {i < STEPS.length - 1 && <span aria-hidden className="mx-2 h-px w-8 bg-line-strong" />}
        </li>
      ))}
    </ol>
  );
}

function DropZone({ onFile, busy }: { onFile: (f: File) => void; busy: boolean }) {
  const input = React.useRef<HTMLInputElement>(null);
  const [over, setOver] = React.useState(false);
  const accept = (files: FileList | null) => {
    const f = files?.[0];
    if (!f) return;
    if (!/\.(xlsx|xls|csv)$/i.test(f.name)) {
      toast.error("Use o arquivo .xlsx exportado da Área do Investidor da B3.");
      return;
    }
    onFile(f);
  };
  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        accept(e.dataTransfer.files);
      }}
      className={cn(
        "flex flex-col items-center rounded-lg border border-dashed px-6 py-12 text-center transition-colors",
        over ? "border-ink bg-sunken" : "border-line-strong bg-surface",
      )}
    >
      <div className="mb-3 rounded-full bg-sunken p-3 text-ink-2">
        <Upload className="size-5" />
      </div>
      <p className="text-lg font-semibold">Arraste o extrato aqui</p>
      <p className="mt-1 max-w-md text-ink-2">Extrato de Negociação ou de Movimentação, em Excel. O tipo é identificado pelo conteúdo.</p>
      <Button variant="primary" className="mt-4" onClick={() => input.current?.click()} disabled={busy}>
        {busy ? "Lendo arquivo…" : "Escolher arquivo"}
      </Button>
      <input ref={input} type="file" accept=".xlsx,.xls,.csv" className="sr-only" onChange={(e) => accept(e.target.files)} />
    </div>
  );
}

function Preview({ preview, onCancel, onCommit, committing }: { preview: ImportPreview; onCancel: () => void; onCommit: () => void; committing: boolean }) {
  const [filter, setFilter] = React.useState<ImportRowStatus | "ALL">("ALL");
  const rows = filter === "ALL" ? preview.rows : preview.rows.filter((r) => r.status === filter);
  const statuses: ImportRowStatus[] = ["NEW", "DUPLICATE", "IGNORED", "ERROR"];
  return (
    <Panel>
      <PanelHeader
        title={
          <span className="flex items-center gap-2">
            <FileSpreadsheet className="size-5 text-ink-2" /> {preview.file_name}
          </span>
        }
        description={`${preview.file_kind === "NEGOTIATION" ? "Extrato de Negociação" : "Extrato de Movimentação"} · ${preview.rows.length} linhas lidas. Nada foi gravado ainda.`}
      />
      <div className="flex flex-wrap gap-2 px-4 pb-3" role="group" aria-label="Filtrar por status">
        <button
          type="button"
          onClick={() => setFilter("ALL")}
          aria-pressed={filter === "ALL"}
          className={cn("rounded-md border px-3 py-1.5 text-sm", filter === "ALL" ? "border-ink text-ink" : "border-line-strong text-ink-2 hover:text-ink")}
        >
          Todas <span className="num font-semibold">{preview.rows.length}</span>
        </button>
        {statuses.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setFilter(s)}
            aria-pressed={filter === s}
            disabled={!preview.counts[s]}
            className={cn(
              "rounded-md border px-3 py-1.5 text-sm disabled:opacity-40",
              filter === s ? "border-ink text-ink" : "border-line-strong text-ink-2 hover:text-ink",
            )}
          >
            {IMPORT_STATUS_LABEL[s]}s <span className="num font-semibold">{preview.counts[s]}</span>
          </button>
        ))}
      </div>
      <Table>
        <THead>
          <TR className="bg-surface-2">
            <TH numeric className="w-12">Linha</TH>
            <TH>Status</TH>
            <TH>Data</TH>
            <TH>Ativo</TH>
            <TH>Movimento</TH>
            <TH>Vira</TH>
            <TH numeric>Quant.</TH>
            <TH numeric>Preço</TH>
            <TH numeric>Valor</TH>
            <TH>Motivo</TH>
          </TR>
        </THead>
        <TBody>
          {rows.map((r) => (
            <TR key={r.line} className={cn(r.status === "IGNORED" && "text-ink-2", r.status === "ERROR" && "bg-down-soft/50")}>
              <TD numeric className="text-muted">{r.line}</TD>
              <TD>
                <Badge tone={STATUS_TONE[r.status]}>{IMPORT_STATUS_LABEL[r.status]}</Badge>
              </TD>
              <TD className="num">{formatDate(r.date)}</TD>
              <TD className="font-semibold">{r.ticker ?? "—"}</TD>
              <TD>{r.kind}</TD>
              <TD>{r.mapped_type ? TX_TYPE_LABEL[r.mapped_type] : <span className="text-muted">—</span>}</TD>
              <TD numeric>{r.quantity && /^[\d.]+$/.test(r.quantity) ? formatQuantity(r.quantity) : (r.quantity ?? "—")}</TD>
              <TD numeric>{r.price ? formatBRL(r.price, { precise: true }) : "—"}</TD>
              <TD numeric>{formatBRL(r.value)}</TD>
              <TD className="max-w-80 whitespace-normal text-sm text-ink-2">{r.reason ?? ""}</TD>
            </TR>
          ))}
        </TBody>
      </Table>
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line bg-surface-2 px-4 py-3">
        <p className="text-sm text-ink-2">
          {preview.counts.NEW} novos serão gravados. Duplicados, ignorados e linhas com erro ficam de fora.
        </p>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={onCancel}>
            Cancelar
          </Button>
          <Button variant="primary" onClick={onCommit} disabled={committing || preview.counts.NEW === 0}>
            {committing ? "Importando…" : `Importar ${preview.counts.NEW} lançamentos`}
          </Button>
        </div>
      </div>
    </Panel>
  );
}

function Report({ result, onAgain }: { result: ImportResult; onAgain: () => void }) {
  const items = [
    { label: "Inseridos", value: result.inserted, tone: "text-up" },
    { label: "Duplicados (já existiam)", value: result.duplicates, tone: "text-ink" },
    { label: "Ignorados (fora do escopo)", value: result.ignored, tone: "text-ink" },
    { label: "Com erro", value: result.errors, tone: result.errors ? "text-down" : "text-ink" },
  ];
  return (
    <Panel className="px-6 py-8">
      <div className="flex items-center gap-3">
        <CheckCircle2 className="size-6 text-up" />
        <h2 className="text-xl font-semibold">Importação concluída</h2>
      </div>
      <dl className="mt-6 grid grid-cols-2 gap-6 md:grid-cols-4">
        {items.map((i) => (
          <div key={i.label}>
            <dt className="text-sm text-ink-2">{i.label}</dt>
            <dd className={cn("num mt-1 text-[2rem] font-semibold leading-none", i.tone)}>{i.value}</dd>
          </div>
        ))}
      </dl>
      <div className="mt-8 flex gap-2">
        <Button asChild variant="primary">
          <Link to="/operacoes?source=B3">Ver lançamentos</Link>
        </Button>
        <Button onClick={onAgain}>Importar outro arquivo</Button>
      </div>
    </Panel>
  );
}

export function ImportarPage() {
  const preview = useImportPreview();
  const commit = useImportCommit();
  const [result, setResult] = React.useState<ImportResult | null>(null);

  const reset = () => {
    preview.reset();
    commit.reset();
    setResult(null);
  };
  const step = result ? 2 : preview.data ? 1 : 0;

  return (
    <>
      <PageTitle title="Importar" description="Traga as operações e os proventos dos extratos da B3. Você revisa tudo antes de gravar." />
      <Steps current={step} />
      {step === 0 && (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
          <DropZone
            busy={preview.isPending}
            onFile={(f) => preview.mutate(f, { onError: (e) => toast.error(e.message) })}
          />
          <aside className="text-ink-2">
            <h2 className="mb-2 font-semibold text-ink">Onde baixar os extratos</h2>
            <p>Na Área do Investidor da B3, abra Extratos e exporte em Excel:</p>
            <ul className="mt-3 flex flex-col gap-3">
              <li>
                <span className="font-medium text-ink">Negociação:</span> compras e vendas. Operações no mercado futuro são ignoradas.
              </li>
              <li>
                <span className="font-medium text-ink">Movimentação:</span> proventos e eventos creditados. As liquidações de compra e venda são ignoradas porque já vêm na Negociação.
              </li>
            </ul>
            <p className="mt-3">Importar o mesmo arquivo de novo não duplica nada.</p>
          </aside>
        </div>
      )}
      {step === 1 && preview.data && (
        <Preview
          preview={preview.data}
          onCancel={reset}
          committing={commit.isPending}
          onCommit={() =>
            commit.mutate(preview.data.id, {
              onSuccess: (r) => {
                setResult(r);
                toast.success(`${r.inserted} lançamentos importados.`);
              },
              onError: (e) => toast.error(e.message),
            })
          }
        />
      )}
      {step === 2 && result && <Report result={result} onAgain={reset} />}
    </>
  );
}
