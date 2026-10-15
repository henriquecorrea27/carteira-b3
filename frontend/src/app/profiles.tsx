import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ChevronDown } from "lucide-react";
import { toast } from "sonner";
import { useProfiles } from "@/api/hooks";
import { setProfileId, useProfileId } from "@/api/profile";
import type { Profile } from "@/api/types";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/menu";

/**
 * Profiles: independent portfolios, each in its own database on the backend (only shown when there is more
 * than one). The first profile keeps the neutral look; the others tint the header so it is always clear
 * which portfolio is open.
 */

const ACCENTS = ["var(--series-7)", "var(--series-1)", "var(--series-5)", "var(--series-2)"];

export function profileAccent(index: number): string | null {
  return index <= 0 ? null : ACCENTS[(index - 1) % ACCENTS.length];
}

export function useActiveProfile(): { profiles: Profile[]; active: Profile | undefined; accent: string | null; multiple: boolean } {
  const id = useProfileId();
  const { data } = useProfiles();
  const profiles = data ?? [];
  const index = Math.max(0, profiles.findIndex((p) => p.id === id));
  return { profiles, active: profiles[index], accent: profileAccent(index), multiple: profiles.length > 1 };
}

function useSwitchProfile() {
  const qc = useQueryClient();
  return React.useCallback(
    async (id: string | null) => {
      await qc.cancelQueries();
      qc.removeQueries(); // nothing of the previous portfolio may show up in the next one
      setProfileId(id); // App remounts the pages (keyed by the profile)
    },
    [qc],
  );
}

function Dot({ color }: { color: string | null }) {
  return <span aria-hidden className="size-2.5 shrink-0 rounded-full" style={{ background: color ?? "var(--ink)" }} />;
}

export function ProfileMenu() {
  const id = useProfileId();
  const { profiles, active, accent, multiple } = useActiveProfile();
  const switchTo = useSwitchProfile();

  // A remembered profile that no longer exists (removed from PROFILES) falls back to the first one
  React.useEffect(() => {
    if (id && profiles.length && !profiles.some((p) => p.id === id)) void switchTo(null);
  }, [id, profiles, switchTo]);

  if (!multiple || !active) return null;
  const onChange = (next: string) => {
    if (next === active.id) return;
    void switchTo(next).then(() => toast.success(`Carteira: ${profiles.find((p) => p.id === next)?.name ?? next}`));
  };
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button size="sm" aria-label={`Carteira aberta: ${active.name}. Trocar de carteira`} title="Trocar de carteira">
          <Dot color={accent} />
          <span className="max-w-[8rem] truncate">{active.name}</span>
          <ChevronDown className="!size-3.5 text-muted" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        <div className="px-2 pb-1 pt-0.5 text-sm text-muted">Carteiras</div>
        <DropdownMenuRadioGroup value={active.id} onValueChange={onChange}>
          {profiles.map((p, i) => (
            <DropdownMenuRadioItem key={p.id} value={p.id}>
              <Dot color={profileAccent(i)} />
              {p.name}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** "Importando para: Pai" and similar notes: names the open portfolio when there is more than one. */
export function ActiveProfileTag({ prefix }: { prefix: string }) {
  const { active, accent, multiple } = useActiveProfile();
  if (!multiple || !active) return null;
  return (
    <span className="inline-flex items-center gap-1.5 rounded-md border border-line bg-surface px-2 py-1 text-sm text-ink-2">
      <Dot color={accent} />
      {prefix} <strong className="font-semibold text-ink">{active.name}</strong>
    </span>
  );
}
