import * as React from "react";
import { Send } from "lucide-react";
import { toast } from "sonner";
import { useReportDispatches, useReportPreview, useSendReport } from "@/api/hooks";
import type { ReportDispatch } from "@/api/types";
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
import { Callout, Skeleton } from "@/components/ui/misc";
import { formatDate } from "@/lib/format";

/** **bold** spans inside a line of the Discord message. */
function Inline({ text }: { text: string }) {
  const parts = text.split(/\*\*(.+?)\*\*/g);
  return (
    <>
      {parts.map((part, i) =>
        i % 2 ? (
          <strong key={i} className="font-semibold text-ink">
            {part}
          </strong>
        ) : (
          <React.Fragment key={i}>{part}</React.Fragment>
        ),
      )}
    </>
  );
}

/** Renders the subset of Discord Markdown the report uses (##, ###, -#, lists, bold). */
export function DiscordMessage({ content }: { content: string }) {
  return (
    <div className="space-y-0.5 text-sm leading-relaxed text-ink-2">
      {content.split("\n").map((line, i) => {
        if (line.startsWith("## "))
          return (
            <p key={i} className="text-base font-semibold text-ink">
              <Inline text={line.slice(3)} />
            </p>
          );
        if (line.startsWith("### "))
          return (
            <p key={i} className="pt-1 font-semibold text-ink">
              <Inline text={line.slice(4)} />
            </p>
          );
        if (line.startsWith("-# "))
          return (
            <p key={i} className="text-xs text-muted">
              <Inline text={line.slice(3)} />
            </p>
          );
        if (line.startsWith("- "))
          return (
            <p key={i} className="flex gap-2 pl-1">
              <span aria-hidden className="text-muted">
                •
              </span>
              <span>
                <Inline text={line.slice(2)} />
              </span>
            </p>
          );
        if (!line.trim()) return <div key={i} className="h-2" />;
        return (
          <p key={i}>
            <Inline text={line} />
          </p>
        );
      })}
    </div>
  );
}

function sentAt(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }).format(d);
}

function DispatchRow({ d }: { d: ReportDispatch }) {
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-sm">
      <span className="tabular-nums text-ink">{sentAt(d.created_at)}</span>
      <span className="text-ink-2">
        {d.trigger === "SCHEDULED" ? "Agendado" : "Manual"} · relatório de {formatDate(d.report_date)}
      </span>
      <span className="ml-auto flex items-center gap-1.5">
        {d.late && <Badge tone="warn">Atrasado</Badge>}
        {d.status === "SENT" ? <Badge tone="up">Enviado</Badge> : <Badge tone="down">Falhou</Badge>}
      </span>
      {d.status === "FAILED" && d.error && <span className="w-full text-xs text-down">{d.error}</span>}
    </li>
  );
}

export function ReportDialog() {
  const [open, setOpen] = React.useState(false);
  const preview = useReportPreview(open);
  const dispatches = useReportDispatches(open);
  const send = useSendReport();
  const data = preview.data;
  const messages = data ? (data.messages.length ? data.messages : [data.content]) : [];

  const onSend = () =>
    send.mutate(undefined, {
      onSuccess: (d) =>
        toast.success(d.messages > 1 ? `Relatório enviado em ${d.messages} mensagens.` : "Relatório enviado ao Discord."),
      onError: (e) => toast.error(e.message),
    });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Relatório diário do Discord" title="Relatório diário do Discord">
          <Send />
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Relatório diário</DialogTitle>
          <DialogDescription>
            Enviado ao Discord nos dias úteis às {data?.report_time ?? "19:00"}, depois de atualizar cotações, proventos e
            decisões. Se o computador estiver desligado nesse horário, sai com atraso quando for ligado. Prévia com os dados
            atuais:
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-4">
          {data && !data.configured && (
            <Callout tone="warn" title="Webhook do Discord não configurado">
              No Discord: Editar canal › Integrações › Webhooks › Novo webhook › Copiar URL do webhook. Cole a URL em{" "}
              <code className="rounded bg-sunken px-1">DISCORD_WEBHOOK_URL</code> no arquivo{" "}
              <code className="rounded bg-sunken px-1">backend/.env</code> e reinicie o backend.
            </Callout>
          )}
          {preview.isError && (
            <Callout tone="error" title="Não foi possível gerar a prévia">
              {preview.error.message}
            </Callout>
          )}

          <section aria-label="Prévia do relatório" className="space-y-2">
            {preview.isPending
              ? Array.from({ length: 3 }, (_, i) => <Skeleton key={i} className="h-24" />)
              : messages.map((m, i) => (
                  <div key={i} className="rounded-lg border border-line bg-surface-2 px-4 py-3">
                    {messages.length > 1 && (
                      <p className="mb-1 text-xs text-muted">
                        Mensagem {i + 1} de {messages.length}
                      </p>
                    )}
                    <DiscordMessage content={m} />
                  </div>
                ))}
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
          <Button variant="primary" onClick={onSend} disabled={!data?.configured || send.isPending}>
            <Send />
            {send.isPending ? "Enviando…" : "Enviar relatório agora"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
