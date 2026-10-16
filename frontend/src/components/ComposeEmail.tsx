import { ActionIcon, Alert, Badge, Button, FileButton, Group, Loader, Modal, Stack, TagsInput, Text, Textarea, TextInput } from '@mantine/core'
import { IconPaperclip, IconSend, IconX } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { api } from '../api'
import { useApiMutation } from '../hooks'

interface ComposeInfo {
  enabled: boolean
  backend: string
  sender: string | null
  reply_to: string | null
  to: string[]
  contact_id: number | null
  unsubscribed: boolean
}

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

/** Write and send an email from inside the CRM (no Outlook / mailto:). It is logged on the timeline. */
export function ComposeEmail({ opened, onClose, contactId, opportunityId }: { opened: boolean; onClose: () => void; contactId?: number; opportunityId?: number }) {
  const { data: info, isLoading } = useQuery({
    queryKey: ['email-compose', contactId, opportunityId],
    queryFn: () => api<ComposeInfo>('/email/compose', { params: { contact_id: contactId, opportunity_id: opportunityId } }),
    enabled: opened,
  })
  const [to, setTo] = useState<string[]>([])
  const [cc, setCc] = useState<string[]>([])
  const [bcc, setBcc] = useState<string[]>([])
  const [showCc, setShowCc] = useState(false)
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [files, setFiles] = useState<File[]>([])

  useEffect(() => {
    if (opened && info) setTo(info.to)
  }, [opened, info])

  const reset = () => {
    setCc([])
    setBcc([])
    setShowCc(false)
    setSubject('')
    setBody('')
    setFiles([])
  }
  const send = useApiMutation(
    () => {
      const form = new FormData()
      form.append('to', to.join(','))
      form.append('cc', cc.join(','))
      form.append('bcc', bcc.join(','))
      form.append('subject', subject)
      form.append('body', body)
      if (info?.contact_id) form.append('contact_id', String(info.contact_id))
      if (opportunityId) form.append('opportunity_id', String(opportunityId))
      files.forEach((f) => form.append('files', f))
      return api('/email/send', { method: 'POST', form })
    },
    {
      invalidate: [['activities']],
      success: 'Email sent',
      onSuccess: () => {
        reset()
        onClose()
      },
    },
  )

  const invalid = [...to, ...cc, ...bcc].filter((a) => !EMAIL.test(a))
  const size = files.reduce((n, f) => n + f.size, 0)
  const canSend = info?.enabled && to.length > 0 && !invalid.length && subject.trim() && body.trim() && size <= 10_000_000

  return (
    <Modal opened={opened} onClose={onClose} title="New email" size="lg">
      {isLoading || !info ? (
        <Group justify="center" p="xl">
          <Loader size="sm" />
        </Group>
      ) : (
        <Stack gap="sm">
          {!info.enabled && (
            <Alert color="orange" variant="light" title="Email is not set up">
              An administrator needs to configure sending (CRM_MAIL_BACKEND: Microsoft 365 or SMTP).
            </Alert>
          )}
          {info.unsubscribed && (
            <Alert color="yellow" variant="light">
              This contact unsubscribed from marketing email. A personal, one-to-one message is fine; do not send promotions.
            </Alert>
          )}
          {info.enabled && (
            <Text size="xs" c="dimmed">
              From <b>{info.sender}</b>
              {info.reply_to ? ` · replies go to ${info.reply_to}` : info.backend === 'graph' ? ' · saved in your Outlook Sent Items' : ''}
            </Text>
          )}
          <Group align="flex-end" gap="xs" wrap="nowrap">
            <TagsInput label="To" value={to} onChange={setTo} splitChars={[',', ';', ' ']} clearable style={{ flex: 1 }} data-autofocus />
            {!showCc && (
              <Button variant="subtle" size="xs" onClick={() => setShowCc(true)}>
                Cc / Bcc
              </Button>
            )}
          </Group>
          {showCc && (
            <Group grow align="flex-start">
              <TagsInput label="Cc" value={cc} onChange={setCc} splitChars={[',', ';', ' ']} />
              <TagsInput label="Bcc" value={bcc} onChange={setBcc} splitChars={[',', ';', ' ']} />
            </Group>
          )}
          {invalid.length > 0 && (
            <Text size="xs" c="red">
              Not a valid address: {invalid.join(', ')}
            </Text>
          )}
          <TextInput label="Subject" value={subject} onChange={(e) => setSubject(e.target.value)} />
          <Textarea
            label="Message"
            description="Blank line = new paragraph · lines starting with “- ” = bullets · **text** = bold"
            autosize
            minRows={8}
            maxRows={20}
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
          {files.length > 0 && (
            <Group gap={6}>
              {files.map((f, i) => (
                <Badge
                  key={`${f.name}-${i}`}
                  variant="light"
                  color="gray"
                  tt="none"
                  leftSection={<IconPaperclip size={12} />}
                  rightSection={
                    <ActionIcon size="xs" variant="transparent" color="gray" aria-label={`Remove ${f.name}`} onClick={() => setFiles(files.filter((_, j) => j !== i))}>
                      <IconX size={12} />
                    </ActionIcon>
                  }
                >
                  {f.name}
                </Badge>
              ))}
            </Group>
          )}
          {size > 10_000_000 && (
            <Text size="xs" c="red">
              Attachments are over 10 MB.
            </Text>
          )}
          <Group justify="space-between">
            <FileButton multiple onChange={(f) => setFiles([...files, ...f])}>
              {(props) => (
                <Button {...props} variant="default" leftSection={<IconPaperclip size={16} />}>
                  Attach
                </Button>
              )}
            </FileButton>
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
            The email is saved on the contact's timeline{opportunityId ? ' and the opportunity' : ''}.
          </Text>
        </Stack>
      )}
    </Modal>
  )
}
