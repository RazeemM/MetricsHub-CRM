import { Button, Checkbox, Group, Modal, Select, SimpleGrid, Stack, Textarea, TextInput } from '@mantine/core'
import { useEffect, useState } from 'react'
import { api } from '../api'
import { useApiMutation, useBrands } from '../hooks'
import { ACCOUNT_TYPES, CONTACT_ROLES, LEAD_SOURCES, LIFECYCLES, toOptions } from '../labels'
import type { Account, Contact } from '../types'
import { AccountPicker, UserPicker } from './common'

type AccountDraft = Partial<Account>

export function AccountFormModal({
  opened,
  onClose,
  account,
  defaults,
  onSaved,
}: {
  opened: boolean
  onClose: () => void
  account?: Account | null
  defaults?: AccountDraft
  onSaved?: (a: Account) => void
}) {
  const [v, setV] = useState<AccountDraft>({})
  useEffect(() => {
    if (opened) setV(account ? { ...account } : { account_type: 'prospect', ...defaults })
  }, [opened, account, defaults])
  const set = (k: keyof Account) => (val: unknown) => setV((s) => ({ ...s, [k]: val }))
  const save = useApiMutation(
    (body: AccountDraft) =>
      account ? api<Account>(`/accounts/${account.id}`, { method: 'PATCH', body }) : api<Account>('/accounts', { method: 'POST', body }),
    {
      invalidate: [['accounts'], ['account']],
      success: account ? 'Account updated' : 'Account created',
      onSuccess: (a) => {
        onSaved?.(a)
        onClose()
      },
    },
  )
  const fields = ['name', 'account_type', 'domain', 'website', 'industry', 'country', 'region', 'city', 'address', 'phone', 'vat_number', 'parent_id', 'owner_id', 'notes'] as const
  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    const body: Record<string, unknown> = {}
    fields.forEach((f) => (body[f] = v[f] === '' ? null : v[f]))
    save.mutate(body as AccountDraft)
  }
  return (
    <Modal opened={opened} onClose={onClose} title={account ? 'Edit account' : 'New account'} size="lg">
      <form onSubmit={submit}>
        <Stack>
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <TextInput label="Name" required value={v.name ?? ''} onChange={(e) => set('name')(e.target.value)} data-autofocus />
            <Select label="Type" data={toOptions(ACCOUNT_TYPES)} value={v.account_type ?? 'prospect'} onChange={set('account_type')} allowDeselect={false} />
            <TextInput label="Email domain" placeholder="company.com" value={v.domain ?? ''} onChange={(e) => set('domain')(e.target.value)} />
            <TextInput label="Website" value={v.website ?? ''} onChange={(e) => set('website')(e.target.value)} />
            <TextInput label="Industry" value={v.industry ?? ''} onChange={(e) => set('industry')(e.target.value)} />
            <TextInput label="Phone" value={v.phone ?? ''} onChange={(e) => set('phone')(e.target.value)} />
            <TextInput label="Country" value={v.country ?? ''} onChange={(e) => set('country')(e.target.value)} />
            <TextInput label="Region / state" value={v.region ?? ''} onChange={(e) => set('region')(e.target.value)} />
            <TextInput label="City" value={v.city ?? ''} onChange={(e) => set('city')(e.target.value)} />
            <TextInput label="VAT number" value={v.vat_number ?? ''} onChange={(e) => set('vat_number')(e.target.value)} />
            <AccountPicker label="Parent account" value={v.parent_id} onChange={set('parent_id')} />
            <UserPicker label="Owner" value={v.owner_id} onChange={set('owner_id')} />
          </SimpleGrid>
          <Textarea label="Address" autosize minRows={2} value={v.address ?? ''} onChange={(e) => set('address')(e.target.value)} />
          <Textarea label="Notes" autosize minRows={2} value={v.notes ?? ''} onChange={(e) => set('notes')(e.target.value)} />
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" loading={save.isPending}>
              Save
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}

type ContactDraft = Partial<Contact>

export function ContactFormModal({
  opened,
  onClose,
  contact,
  defaults,
  onSaved,
}: {
  opened: boolean
  onClose: () => void
  contact?: Contact | null
  defaults?: ContactDraft
  onSaved?: (c: Contact) => void
}) {
  const { data: brands } = useBrands()
  const [v, setV] = useState<ContactDraft>({})
  useEffect(() => {
    if (opened) setV(contact ? { ...contact } : { role: 'customer_contact', lifecycle: 'lead', source: 'direct', ...defaults })
  }, [opened, contact, defaults])
  const set = (k: keyof Contact) => (val: unknown) => setV((s) => ({ ...s, [k]: val }))
  const save = useApiMutation(
    (body: ContactDraft) =>
      contact ? api<Contact>(`/contacts/${contact.id}`, { method: 'PATCH', body }) : api<Contact>('/contacts', { method: 'POST', body }),
    {
      invalidate: [['contacts'], ['contact'], ['accounts'], ['account']],
      success: contact ? 'Contact updated' : 'Contact created',
      onSuccess: (c) => {
        onSaved?.(c)
        onClose()
      },
    },
  )
  const fields = ['first_name', 'last_name', 'email', 'phone', 'mobile', 'job_title', 'account_id', 'role', 'lifecycle', 'source', 'brand_id', 'owner_id', 'country', 'linkedin', 'consent_marketing', 'unsubscribed', 'notes'] as const
  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    const body: Record<string, unknown> = {}
    fields.forEach((f) => (body[f] = v[f] === '' ? null : v[f]))
    save.mutate(body as ContactDraft)
  }
  return (
    <Modal opened={opened} onClose={onClose} title={contact ? 'Edit contact' : 'New contact'} size="lg">
      <form onSubmit={submit}>
        <Stack>
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <TextInput label="First name" value={v.first_name ?? ''} onChange={(e) => set('first_name')(e.target.value)} data-autofocus />
            <TextInput label="Last name" value={v.last_name ?? ''} onChange={(e) => set('last_name')(e.target.value)} />
            <TextInput label="Email" type="email" value={v.email ?? ''} onChange={(e) => set('email')(e.target.value)} />
            <TextInput label="Job title" value={v.job_title ?? ''} onChange={(e) => set('job_title')(e.target.value)} />
            <TextInput label="Phone" value={v.phone ?? ''} onChange={(e) => set('phone')(e.target.value)} />
            <TextInput label="Mobile" value={v.mobile ?? ''} onChange={(e) => set('mobile')(e.target.value)} />
            <AccountPicker label="Account" value={v.account_id} initialLabel={contact?.account?.name} onChange={set('account_id')} />
            <Select label="Role" data={toOptions(CONTACT_ROLES)} value={v.role ?? 'customer_contact'} onChange={set('role')} allowDeselect={false} />
            <Select label="Lifecycle" data={toOptions(LIFECYCLES)} value={v.lifecycle ?? 'lead'} onChange={set('lifecycle')} allowDeselect={false} />
            <Select label="Source" data={toOptions(LEAD_SOURCES)} value={v.source ?? null} onChange={set('source')} clearable />
            <Select
              label="Brand interest"
              data={(brands ?? []).map((b) => ({ value: String(b.id), label: b.name }))}
              value={v.brand_id ? String(v.brand_id) : null}
              onChange={(x) => set('brand_id')(x ? Number(x) : null)}
              clearable
            />
            <UserPicker label="Owner" value={v.owner_id} onChange={set('owner_id')} />
            <TextInput label="Country" value={v.country ?? ''} onChange={(e) => set('country')(e.target.value)} />
            <TextInput label="LinkedIn" value={v.linkedin ?? ''} onChange={(e) => set('linkedin')(e.target.value)} />
          </SimpleGrid>
          <Group>
            <Checkbox label="Marketing consent (opt-in)" checked={!!v.consent_marketing} onChange={(e) => set('consent_marketing')(e.currentTarget.checked)} />
            <Checkbox label="Unsubscribed" checked={!!v.unsubscribed} onChange={(e) => set('unsubscribed')(e.currentTarget.checked)} />
          </Group>
          <Textarea label="Notes" autosize minRows={2} value={v.notes ?? ''} onChange={(e) => set('notes')(e.target.value)} />
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" loading={save.isPending}>
              Save
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  )
}
