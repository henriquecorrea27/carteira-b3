import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./endpoints";
import type { TransactionFilters, TransactionInput } from "./types";

export const queryKeys = {
  summary: ["portfolio", "summary"] as const,
  positions: ["portfolio", "positions"] as const,
  pending: ["portfolio", "pending"] as const,
  equity: ["portfolio", "equity"] as const,
  returns: ["portfolio", "returns"] as const,
  transactions: (f: TransactionFilters) => ["transactions", f] as const,
  dividends: ["dividends"] as const,
  search: (q: string) => ["assets", "search", q] as const,
  analysis: (t: string) => ["analysis", t] as const,
  priceBars: (t: string) => ["prices", t] as const,
};

export const useSummary = () => useQuery({ queryKey: queryKeys.summary, queryFn: api.getSummary });
export const usePositions = () => useQuery({ queryKey: queryKeys.positions, queryFn: api.getPositions });
export const usePending = () => useQuery({ queryKey: queryKeys.pending, queryFn: api.getPending });
export const useEquitySeries = () => useQuery({ queryKey: queryKeys.equity, queryFn: api.getEquitySeries });
export const useReturnSeries = () => useQuery({ queryKey: queryKeys.returns, queryFn: api.getReturnSeries });
export const useDividends = () => useQuery({ queryKey: queryKeys.dividends, queryFn: api.getDividends });

export const useTransactions = (filters: TransactionFilters) =>
  useQuery({
    queryKey: queryKeys.transactions(filters),
    queryFn: () => api.getTransactions(filters),
    placeholderData: keepPreviousData,
  });

export const useAssetSearch = (q: string, enabled = true) =>
  useQuery({
    queryKey: queryKeys.search(q),
    queryFn: () => api.searchAssets(q),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  });

export const useAnalysis = (ticker: string | null) =>
  useQuery({
    queryKey: queryKeys.analysis(ticker ?? ""),
    queryFn: () => api.getAnalysis(ticker!),
    enabled: Boolean(ticker),
    retry: false,
  });

export const usePriceBars = (ticker: string | null) =>
  useQuery({
    queryKey: queryKeys.priceBars(ticker ?? ""),
    queryFn: () => api.getPriceBars(ticker!),
    enabled: Boolean(ticker),
  });

/** Anything that changes the ledger invalidates portfolio-derived data too. */
function useInvalidateLedger() {
  const qc = useQueryClient();
  return () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: ["transactions"] }),
      qc.invalidateQueries({ queryKey: ["portfolio"] }),
      qc.invalidateQueries({ queryKey: ["dividends"] }),
    ]);
}

export function useCreateTransaction() {
  const invalidate = useInvalidateLedger();
  return useMutation({ mutationFn: (input: TransactionInput) => api.createTransaction(input), onSuccess: invalidate });
}

export function useCreateTransactionsBatch() {
  const invalidate = useInvalidateLedger();
  return useMutation({
    mutationFn: (inputs: TransactionInput[]) => api.createTransactionsBatch(inputs),
    onSuccess: invalidate,
  });
}

export function useUpdateTransaction() {
  const invalidate = useInvalidateLedger();
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: TransactionInput }) => api.updateTransaction(id, input),
    onSuccess: invalidate,
  });
}

export function useDeleteTransaction() {
  const invalidate = useInvalidateLedger();
  return useMutation({ mutationFn: (id: number) => api.deleteTransaction(id), onSuccess: invalidate });
}

export function useRefreshPrices() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.refreshPrices,
    onSuccess: () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: ["portfolio"] }),
        qc.invalidateQueries({ queryKey: ["prices"] }),
        qc.invalidateQueries({ queryKey: ["analysis"] }),
      ]),
  });
}

export function useImportPreview() {
  return useMutation({ mutationFn: (file: File) => api.previewImport(file) });
}

export function useImportCommit() {
  const invalidate = useInvalidateLedger();
  return useMutation({ mutationFn: (previewId: string) => api.commitImport(previewId), onSuccess: invalidate });
}
