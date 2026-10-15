import { Alert, Badge, Button, Group, Loader, Modal, Stack, TagsInput, Text, Textarea, TextInput } from '@mantine/core'
import { IconPaperclip, IconSend } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { api } from '../api'
import { useApiMutation } from '../hooks'

interface EmailDraft {
  enabled: boolean
  sender: string
  to: string[]
  cc: string[]
  subject: string
  body: string
  attachment: string
}

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export function EmailQuote({ quoteId, opportunityId, onClose }: { quoteId: number | null; opportunityId: number; onClose: () => void }) {
  const { data: draft, isLoading } = useQuery({
    queryKey: ['quote-email', quoteId],
    queryFn: () => api<EmailDraft>(`/quotes/${quoteId}/email`),
    enabled: quoteId !== null,
    gcTime: 0,
  })
  const [to, setTo] = useState<string[]>([])
  const [cc, setCc] = useState<string[]>([])
  const [bcc, setBcc] = useState<string[]>([])
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')

  useEffect(() => {
    if (!draft) return
    setTo(draft.to)
    setCc(draft.cc)
    setBcc([])
    setSubject(draft.subject)
    setBody(draft.body)
  }, [draft])

  const send = useApiMutation(() => api(`/quotes/${quoteId}/email`, { method: 'POST', body: { to, cc, bcc, subject, body } }), {
    invalidate: [['quotes', opportunityId], ['activities']],
    success: 'Quote sent',
    onSuccess: onClose,
  })

  const invalid = [...to, ...cc, ...bcc].filter((a) => !EMAIL.test(a))
  const canSend = draft?.enabled && to.length > 0 && invalid.length === 0 && subject.trim() && body.trim()

  return (
    <Modal opened={quoteId !== null} onClose={onClose} title="Email quote" size="lg">
      {isLoading || !draft ? (
        <Group justify="center" p="xl">
          <Loader size="sm" />
        </Group>
      ) : (
        <Stack gap="sm">
          {!draft.enabled && (
            <Alert color="orange" variant="light" title="Email is not set up">
              An administrator needs to connect the CRM to Microsoft 365 (CRM_MAIL_BACKEND=graph). You can still download the PDF and attach it yourself.
            </Alert>
          )}
          <TextInput label="From" value={draft.sender} readOnly variant="filled" description="Sent through Microsoft 365; a copy is kept in Sent Items" />
          <TagsInput label="To" value={to} onChange={setTo} placeholder="Type an address and press Enter" splitChars={[',', ';', ' ']} clearable />
          <Group grow align="flex-start">
            <TagsInput label="Cc" value={cc} onChange={setCc} splitChars={[',', ';', ' ']} />
            <TagsInput label="Bcc" value={bcc} onChange={setBcc} splitChars={[',', ';', ' ']} />
          </Group>
          {invalid.length > 0 && (
            <Text size="xs" c="red">
              Not a valid address: {invalid.join(', ')}
            </Text>
          )}
          <TextInput label="Subject" value={subject} onChange={(e) => setSubject(e.target.value)} />
          <Textarea label="Message" autosize minRows={8} maxRows={18} value={body} onChange={(e) => setBody(e.target.value)} />
          <Group justify="space-between">
            <Badge variant="light" color="gray" leftSection={<IconPaperclip size={12} />} tt="none">
              {draft.attachment}
            </Badge>
            <Group gap="xs">
              <Button variant="default" onClick={onClose}>
                Cancel
              </Button>
              <Button leftSection={<IconSend size={16} />} disabled={!canSend} loading={send.isPending} onClick={() => send.mutate(undefined)}>
                Send
              </Button>
            </Group>
          </Group>
          <Text size="xs" c="dimmed">
            A draft quote is marked as sent, and the email is logged on the opportunity.
          </Text>
        </Stack>
      )}
    </Modal>
  )
}
