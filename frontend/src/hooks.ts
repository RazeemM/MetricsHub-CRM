import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { notifications } from '@mantine/notifications'
import { api } from './api'
import type { Account, Brand, Contact, Page, Pipeline, PriceBook, Product, User } from './types'

export const useBrands = () => useQuery({ queryKey: ['brands'], queryFn: () => api<Brand[]>('/brands'), staleTime: 300_000 })
export const useUsers = () => useQuery({ queryKey: ['users'], queryFn: () => api<User[]>('/users'), staleTime: 60_000 })
export const usePipelines = () =>
  useQuery({ queryKey: ['pipelines'], queryFn: () => api<Pipeline[]>('/pipelines'), staleTime: 300_000 })
export const useProducts = (brandId?: number | null) =>
  useQuery({
    queryKey: ['products', brandId ?? null],
    queryFn: () => api<Product[]>('/products', { params: { brand_id: brandId ?? undefined } }),
  })
export const usePriceBooks = () => useQuery({ queryKey: ['price-books'], queryFn: () => api<PriceBook[]>('/price-books') })

export const usePlatforms = () =>
  useQuery({
    queryKey: ['accounts', 'platforms'],
    queryFn: () => api<Page<Account>>('/accounts', { params: { account_type: ['platform_partner'], page_size: 200 } }),
    staleTime: 60_000,
  })

export const useAccountSearch = (q: string, types?: string[]) =>
  useQuery({
    queryKey: ['accounts', 'search', q, types],
    queryFn: () => api<Page<Account>>('/accounts', { params: { q, account_type: types, page_size: 20 } }),
  })

export const useContactSearch = (q: string, accountId?: number | null, role?: string[]) =>
  useQuery({
    queryKey: ['contacts', 'search', q, accountId, role],
    queryFn: () => api<Page<Contact>>('/contacts', { params: { q, account_id: accountId ?? undefined, role, page_size: 20 } }),
  })

/** Mutation helper: shows success/error toasts and invalidates the given query keys. */
export function useApiMutation<TVars, TResult = unknown>(
  fn: (vars: TVars) => Promise<TResult>,
  opts: { invalidate?: string[][]; success?: string; onSuccess?: (r: TResult) => void } = {},
) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: (r) => {
      opts.invalidate?.forEach((k) => qc.invalidateQueries({ queryKey: k }))
      if (opts.success) notifications.show({ color: 'green', message: opts.success })
      opts.onSuccess?.(r)
    },
    onError: (e: Error) => notifications.show({ color: 'red', title: 'Error', message: e.message }),
  })
}
