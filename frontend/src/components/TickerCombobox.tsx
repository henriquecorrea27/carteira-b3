import * as React from "react";
import { Command } from "cmdk";
import { ChevronsUpDown, Search } from "lucide-react";
import { useAssetSearch } from "@/api/hooks";
import { ASSET_CLASS_SINGULAR } from "@/lib/labels";
import { cn } from "@/lib/utils";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/menu";

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = React.useState(value);
  React.useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

/** Ticker field with autocomplete. Accepts tickers not in the list too (typed + Enter). */
export function TickerCombobox({
  id,
  value,
  onChange,
  invalid,
  placeholder = "Buscar ticker",
}: {
  id?: string;
  value: string;
  onChange: (ticker: string) => void;
  invalid?: boolean;
  placeholder?: string;
}) {
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const debounced = useDebounced(query, 150);
  const search = useAssetSearch(debounced, open);
  const typed = query.trim().toUpperCase();
  const results = search.data ?? [];
  const looksLikeTicker = /^[A-Z]{4}\d{1,2}F?$/.test(typed);
  const showTyped = looksLikeTicker && !results.some((r) => r.ticker === typed);

  const pick = (ticker: string) => {
    onChange(ticker.toUpperCase().replace(/^([A-Z]{4}\d{1,2})F$/, "$1"));
    setOpen(false);
    setQuery("");
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          id={id}
          type="button"
          role="combobox"
          aria-expanded={open}
          aria-invalid={invalid || undefined}
          className={cn(
            "flex h-9 w-full items-center justify-between rounded-md border border-line-strong bg-surface px-2.5 text-left text-base hover:border-ink-2/40 focus-visible:border-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink/10 aria-[invalid=true]:border-down",
            !value && "text-muted",
          )}
        >
          <span className={cn(value && "font-semibold")}>{value || placeholder}</span>
          <ChevronsUpDown className="size-4 text-muted" />
        </button>
      </PopoverTrigger>
      <PopoverContent portal={false} className="w-[var(--radix-popover-trigger-width)] min-w-64 p-0">
        <Command shouldFilter={false} label="Buscar ativo">
          <div className="flex items-center gap-2 border-b border-line px-2.5">
            <Search className="size-4 text-muted" />
            <Command.Input
              value={query}
              onValueChange={setQuery}
              onKeyDown={(e) => {
                // Typed fast and hit Enter before results arrived: accept a well-formed ticker as is.
                if (e.key === "Enter" && results.length === 0 && looksLikeTicker) {
                  e.preventDefault();
                  pick(typed);
                }
              }}
              placeholder="Ticker ou nome da empresa"
              className="h-9 w-full bg-transparent text-base outline-none placeholder:text-muted"
            />
          </div>
          <Command.List className="max-h-64 overflow-y-auto p-1">
            {search.isFetching && results.length === 0 && <div className="px-2 py-3 text-sm text-muted">Buscando…</div>}
            {!search.isFetching && results.length === 0 && !showTyped && (
              <Command.Empty className="px-2 py-3 text-sm text-muted">Nenhum ativo encontrado.</Command.Empty>
            )}
            {results.map((r) => (
              <Command.Item
                key={r.ticker}
                value={r.ticker}
                onSelect={() => pick(r.ticker)}
                className="flex cursor-default items-center gap-2 rounded-sm px-2 py-1.5 data-[selected=true]:bg-sunken"
              >
                <span className="w-16 font-semibold">{r.ticker}</span>
                <span className="min-w-0 flex-1 truncate text-sm text-ink-2">{r.name}</span>
                <span className="text-xs text-muted">{ASSET_CLASS_SINGULAR[r.asset_class]}</span>
              </Command.Item>
            ))}
            {showTyped && (
              <Command.Item
                value={`typed-${typed}`}
                onSelect={() => pick(typed)}
                className="flex cursor-default items-center gap-2 rounded-sm px-2 py-1.5 text-sm data-[selected=true]:bg-sunken"
              >
                Usar <span className="font-semibold">{typed}</span>
              </Command.Item>
            )}
          </Command.List>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
