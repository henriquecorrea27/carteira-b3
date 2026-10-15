import * as React from "react";
import { Link } from "react-router-dom";
import { Check, Eye, MessageSquareText, Pencil, Plus, Send, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import {
  useAddWatch,
  useEditWatch,
  useRemoveWatch,
  useSendWatchlist,
  useWatchlist,
  useWatchlistDispatches,
  useWatchlistPreview,
} from "@/api/hooks";
import type { SmaZone, WatchItem, Watchlist } from "@/api/types";
import { TickerCombobox } from "@/components/TickerCombobox";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/form";
import { Callout, EmptyState, Panel, PanelHeader, Skeleton } from "@/components/ui/misc";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { formatBRL, formatDate, formatNumber, toNumber } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useActiveProfile } from "@/app/profiles";
import { DiscordMessage, DispatchRow } from "../relatorio/ReportDialog";
import { PageTitle, QueryError } from "../shared";

type ZoneUi = { tone: "up" | "warn" | "neutral" | "down"; label: (w: Watchlist) => string; short: (w: Watchlist) => string; dot: string };

const ZONE: Record<SmaZone, ZoneUi> = {
  CHEAP: {
    tone: "up",
    label: (w) => `${formatNumber(Math.abs(Number(w.cheap_pct)))}% ou mais abaixo`,
    short: (w) => `≤ −${formatNumber(Math.abs(Number(w.cheap_pct)))}%`,
    dot: "bg-up",
  },
  BELOW: { tone: "warn", label: (w) => `Abaixo da MM${w.sma_days}`, short: () => "Abaixo", dot: "bg-warn" },
  ABOVE: { tone: "neutral", label: (w) => `Acima da MM${w.sma_days}`, short: () => "Acima", dot: "bg-ink-2" },
  EXPENSIVE: {
    tone: "down",
    label: (w) => `${formatNumber(Number(w.expensive_pct))}% ou mais acima`,
    short: (w) => `≥ +${formatNumber(Number(w.expensive_pct))}%`,
    dot: "bg-down",
  },
};

/** −12,4% · +3,9% (one decimal, explicit sign, like the Discord message). */
function distance(pct: string | null): string {
  const n = toNumber(pct);
  if (n === null) return "—";
  const v = Math.round(n * 10) / 10;
  return `${v > 0 ? "+" : v < 0 ? "−" : ""}${formatNumber(Math.abs(v), { minDecimals: 1, maxDecimals: 1 })}%`;
}

/** Where the price sits between −2× and +2× the zone limits, with the SMA in the middle. */
function DistanceBar({ item, w }: { item: WatchItem; w: Watchlist }) {
  const d = toNumber(item.distance_pct);
  if (d === null || !item.zone) return <span className="text-sm text-muted">—</span>;
  const span = 2 * Math.max(Math.abs(Number(w.cheap_pct)), Number(w.expensive_pct)); // ±20%
  const pos = Math.min(Math.max((d + span) / (2 * span), 0), 1) * 100;
  const cheapAt = ((Number(w.cheap_pct) + span) / (2 * span)) * 100;
  const expensiveAt = ((Number(w.expensive_pct) + span) / (2 * span)) * 100;
  return (
    <div className="relative h-2.5 w-36" role="img" aria-label={`${distance(item.distance_pct)} da MM${w.sma_days}`}>
      <div className="absolute inset-y-0.5 left-0 rounded-l-full bg-up-soft" style={{ width: `${cheapAt}%` }} />
      <div className="absolute inset-y-0.5 bg-sunken" style={{ left: `${cheapAt}%`, right: `${100 - expensiveAt}%` }} />
      <div className="absolute inset-y-0.5 right-0 rounded-r-full bg-down-soft" style={{ width: `${100 - expensiveAt}%` }} />
      <div className="absolute inset-y-0 left-1/2 w-px bg-line-strong" />
      <div
        className={cn("absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-surface", ZONE[item.zone].dot)}
        style={{ left: `${pos}%` }}
      />
    </div>
  );
}

function NoteCell({ item }: { item: WatchItem }) {
  const [editing, setEditing] = React.useState(false);
  const [value, setValue] = React.useState(item.note ?? "");
  const edit = useEditWatch();
  const save = () =>
    edit.mutate(
      { ticker: item.ticker, note: value.trim() },
      { onSuccess: () => setEditing(false), onError: (e) => toast.error(e.message) },
    );
  if (editing)
    return (
      <form
        className="flex items-center gap-1"
        onSubmit={(e) => {
          e.preventDefault();
          save();
        }}
      >
        <Input
          autoFocus
          value={value}
          maxLength={300}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === "Escape" && setEditing(false)}
          className="h-8 min-w-40"
          aria-label={`Nota de ${item.ticker}`}
        />
        <Button type="submit" size="icon-sm" variant="ghost" aria-label="Salvar nota" disabled={edit.isPending}>
          <Check />
        </Button>
        <Button type="button" size="icon-sm" variant="ghost" aria-label="Cancelar" onClick={() => setEditing(false)}>
          <X />
        </Button>
      </form>
    );
  return (
    <button
      type="button"
      onClick={() => {
        setValue(item.note ?? "");
        setEditing(true);
      }}
      className="group flex max-w-64 items-center gap-1.5 text-left text-sm text-ink-2 hover:text-ink"
      title="Editar nota"
    >
      <span className={cn("truncate", !item.note && "text-muted")}>{item.note || "Adicionar nota"}</span>
      <Pencil className="size-3.5 shrink-0 opacity-0 group-hover:opacity-100" aria-hidden />
    </button>
  );
}

function AddForm() {
  const [ticker, setTicker] = React.useState("");
  const [note, setNote] = React.useState("");
  const add = useAddWatch();
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!ticker) return;
    add.mutate(
      { ticker, note: note.trim() || undefined },
      {
        onSuccess: () => {
          toast.success(`${ticker} entrou na lista de observação.`);
          setTicker("");
          setNote("");
        },
        onError: (err) => toast.error(err.message),
      },
    );
  };
  return (
    <form onSubmit={submit} className="flex flex-wrap items-end gap-3 px-4 pb-4">
      <Field label="Ação" htmlFor="watch-ticker" className="w-full sm:w-56">
        <TickerCombobox id="watch-ticker" value={ticker} onChange={setTicker} placeholder="Buscar ticker" />
      </Field>
      <Field label="Nota" htmlFor="watch-note" optional className="min-w-0 flex-1 basis-56">
        <Input id="watch-note" value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} placeholder="Ex.: comprar perto da MM200" />
      </Field>
      <Button type="submit" variant="primary" disabled={!ticker || add.isPending}>
        <Plus /> {add.isPending ? "Adicionando…" : "Adicionar"}
      </Button>
    </form>
  );
}

function MessageDialog({ w }: { w: Watchlist }) {
  const [open, setOpen] = React.useState(false);
  const preview = useWatchlistPreview(open);
  const dispatches = useWatchlistDispatches(open);
  const send = useSendWatchlist();
  const messages = preview.data ? (preview.data.messages.length ? preview.data.messages : [preview.data.content]) : [];
  const onSend = () =>
    send.mutate(undefined, {
      onSuccess: () => {
        toast.success("Lista de observação enviada ao Discord.");
        dispatches.refetch();
      },
      onError: (e) => toast.error(e.message),
    });
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <MessageSquareText /> Ver mensagem
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Aviso da lista de observação</DialogTitle>
          <DialogDescription>
            Enviado ao Discord nos dias úteis às {w.report_time}, logo depois do relatório diário
            {w.channel === "SEPARATE" ? ", no canal próprio da lista" : w.channel === "SHARED" ? ", no mesmo canal do relatório" : ""}. Prévia com as
            cotações atuais:
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-4">
          {preview.isError && (
            <Callout tone="error" title="Não foi possível gerar a prévia">
              {preview.error.message}
            </Callout>
          )}
          <section aria-label="Prévia do aviso" className="space-y-2">
            {preview.isPending ? (
              <Skeleton className="h-40" />
            ) : (
              messages.map((m, i) => (
                <div key={i} className="rounded-lg border border-line bg-surface-2 px-4 py-3">
                  <DiscordMessage content={m} />
                </div>
              ))
            )}
          </section>
          <section aria-label="Últimos envios">
            <h3 className="text-sm font-semibold text-ink">Últimos envios</h3>
            {dispatches.data?.length ? (
              <ul className="divide-y divide-line">
                {dispatches.data.map((d) => (
                  <DispatchRow key={d.id} d={d} />
                ))}
              </ul>
            ) : (
              <p className="pt-1 text-sm text-muted">{dispatches.isPending ? "Carregando…" : "Nenhum envio ainda."}</p>
            )}
          </section>
        </DialogBody>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="ghost">Fechar</Button>
          </DialogClose>
          <Button variant="primary" onClick={onSend} disabled={!w.channel || w.items.length === 0 || send.isPending}>
            <Send /> {send.isPending ? "Enviando…" : "Enviar agora"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ChannelNotice({ channel }: { channel: Watchlist["channel"] }) {
  if (channel === "SEPARATE") return null;
  const how = (
    <>
      No canal novo do Discord: Editar canal › Integrações › Webhooks › Novo webhook › Copiar URL do webhook. Cole em{" "}
      <code className="rounded bg-sunken px-1">DISCORD_WATCHLIST_WEBHOOK_URL</code> no <code className="rounded bg-sunken px-1">backend/.env</code> e
      reinicie o app.
    </>
  );
  return channel === "SHARED" ? (
    <Callout tone="info" title="Os avisos estão indo para o mesmo canal do relatório diário">
      Para separar (recomendado, assim a lista não se mistura com o relatório e você pode silenciar um sem o outro): {how}
    </Callout>
  ) : (
    <Callout tone="warn" title="Nenhum webhook do Discord configurado">
      {how}
    </Callout>
  );
}

function WatchTable({ w }: { w: Watchlist }) {
  const remove = useRemoveWatch();
  return (
    <Table>
      <THead>
        <TR>
          <TH>Ação</TH>
          <TH numeric className="hidden sm:table-cell">Preço</TH>
          <TH numeric className="hidden sm:table-cell">
            MM{w.sma_days}
          </TH>
          <TH numeric>Distância</TH>
          <TH className="hidden md:table-cell">
            <span className="sr-only">Posição em relação à média</span>
          </TH>
          <TH>Faixa</TH>
          <TH className="hidden lg:table-cell">Nota</TH>
          <TH>
            <span className="sr-only">Ações</span>
          </TH>
        </TR>
      </THead>
      <TBody>
        {w.items.map((item) => (
          <TR key={item.ticker}>
            <TD>
              <Link to={`/analise/${item.ticker}`} className="block min-w-0 leading-tight hover:underline">
                <span className="font-semibold">{item.ticker}</span>
                {item.name && <span className="block max-w-[7rem] truncate text-sm text-ink-2 sm:max-w-[12rem]">{item.name}</span>}
              </Link>
            </TD>
            <TD numeric className="num hidden sm:table-cell">
              {formatBRL(item.price)}
            </TD>
            <TD numeric className="num hidden text-ink-2 sm:table-cell">
              {formatBRL(item.sma)}
            </TD>
            <TD numeric className="num font-semibold">
              {distance(item.distance_pct)}
            </TD>
            <TD className="hidden md:table-cell">
              <DistanceBar item={item} w={w} />
            </TD>
            <TD>
              {item.zone ? (
                <Badge tone={ZONE[item.zone].tone} title={ZONE[item.zone].label(w)}>
                  <span className="sm:hidden">{ZONE[item.zone].short(w)}</span>
                  <span className="hidden sm:inline">{ZONE[item.zone].label(w)}</span>
                </Badge>
              ) : (
                <span className="text-sm text-muted" title={`A MM${w.sma_days} precisa de ${w.sma_days} pregões`}>
                  {item.price === null ? "Sem cotações" : `Só ${item.sessions} pregões`}
                </span>
              )}
            </TD>
            <TD className="hidden lg:table-cell">
              <NoteCell item={item} />
            </TD>
            <TD numeric>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={`Tirar ${item.ticker} da lista`}
                title="Tirar da lista"
                disabled={remove.isPending}
                onClick={() =>
                  remove.mutate(item.ticker, {
                    onSuccess: () => toast.success(`${item.ticker} saiu da lista de observação.`),
                    onError: (e) => toast.error(e.message),
                  })
                }
              >
                <Trash2 />
              </Button>
            </TD>
          </TR>
        ))}
      </TBody>
    </Table>
  );
}

export function ObservacaoPage() {
  const list = useWatchlist();
  const w = list.data;
  const discord = useActiveProfile().active?.discord !== false;
  const asOf = w?.items.map((i) => i.price_date).filter((d): d is string => Boolean(d)).sort().at(-1);
  return (
    <div className="flex flex-col gap-5">
      <PageTitle
        title="Lista de observação"
        description={
          discord ? (
            <>
              Ações que você acompanha. Todo dia útil às {w?.report_time ?? "19:00"} o Discord recebe só a posição do preço em relação à
              MM{w?.sma_days ?? 200}, com destaque para as que mudaram de faixa desde o último aviso.
            </>
          ) : (
            <>
              Ações que você acompanha, com a posição do preço em relação à MM{w?.sma_days ?? 200}. Esta carteira não envia avisos ao
              Discord: a lista fica só aqui na tela.
            </>
          )
        }
        actions={w && discord && <MessageDialog w={w} />}
      />
      {w && discord && <ChannelNotice channel={w.channel} />}
      <Panel>
        <PanelHeader title="Adicionar ação" description="Qualquer ativo da B3 com cotação no Yahoo Finance (ações, FIIs, ETFs, BDRs)." />
        <AddForm />
      </Panel>
      <Panel>
        <PanelHeader
          title={w ? `Na lista (${w.items.length})` : "Na lista"}
          description={
            w && (
              <>
                Da mais abaixo para a mais acima da MM{w.sma_days} (média dos últimos {w.sma_days} fechamentos diários, ajustados).
                {asOf && ` Cotações de ${formatDate(asOf)}.`}
              </>
            )
          }
        />
        {list.isPending ? (
          <div className="space-y-2 px-4 pb-4">
            <Skeleton className="h-12" />
            <Skeleton className="h-12" />
          </div>
        ) : list.isError ? (
          <div className="px-4 pb-4">
            <QueryError what="a lista de observação" error={list.error} onRetry={() => list.refetch()} />
          </div>
        ) : w!.items.length === 0 ? (
          <EmptyState icon={Eye} title="Sua lista está vazia">
            Adicione as ações que você quer acompanhar. Também dá para usar o botão “Observar” na tela de Análise.
          </EmptyState>
        ) : (
          <WatchTable w={w!} />
        )}
      </Panel>
    </div>
  );
}
