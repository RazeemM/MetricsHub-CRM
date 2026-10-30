import { Anchor, Badge, Card, CloseButton, Grid, Group, NavLink, ScrollArea, Stack, Text, TextInput, Title } from '@mantine/core'
import { IconArrowLeft, IconArrowRight, IconSearch } from '@tabler/icons-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useAuth } from '../auth'
import { PageHeader } from '../components/common'
import { Markdown, plain } from '../help/Markdown'
import { GROUPS, TOPICS, type HelpTopic } from '../help/topics'

const TEXT = new Map(TOPICS.map((t) => [t.id, `${t.title} ${t.summary} ${plain(t.body)}`.toLowerCase()]))

/** The sentence around the first match, for search results. */
function snippet(t: HelpTopic, words: string[]): string {
  const text = plain(t.body)
  const lower = text.toLowerCase()
  const at = Math.min(...words.map((w) => lower.indexOf(w)).filter((n) => n >= 0))
  if (!Number.isFinite(at)) return t.summary
  const start = Math.max(0, text.lastIndexOf('.', at) + 1)
  const s = text.slice(start, start + 180).trim()
  return s.charAt(0).toUpperCase() + s.slice(1) + (text.length > start + 180 ? '…' : '')
}

export default function Help() {
  const { topic } = useParams()
  const nav = useNavigate()
  const { isAdmin } = useAuth()
  const [q, setQ] = useState('')
  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [topic])
  const visible = useMemo(() => TOPICS.filter((t) => isAdmin || !t.admin), [isAdmin])
  const current = TOPICS.find((t) => t.id === topic) ?? visible[0]
  const words = q.toLowerCase().split(/\s+/).filter((w) => w.length > 1)
  const results = words.length ? visible.filter((t) => words.every((w) => TEXT.get(t.id)!.includes(w))) : []
  const index = visible.findIndex((t) => t.id === current.id)
  const prev = index > 0 ? visible[index - 1] : null
  const next = index >= 0 && index < visible.length - 1 ? visible[index + 1] : null

  return (
    <>
      <PageHeader title="Help" subtitle="How to use the CRM, how to configure it, and good practice" />
      <Grid gutter="lg">
        <Grid.Col span={{ base: 12, md: 3 }}>
          <Card withBorder p="xs" style={{ position: 'sticky', top: 76 }}>
            <TextInput
              placeholder="Search the help"
              leftSection={<IconSearch size={16} />}
              rightSection={q ? <CloseButton size="sm" aria-label="Clear search" onClick={() => setQ('')} /> : undefined}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              mb="xs"
              aria-label="Search the help"
            />
            <ScrollArea.Autosize mah="calc(100vh - 200px)" type="auto" offsetScrollbars>
              {GROUPS.map((g) => {
                const items = visible.filter((t) => t.group === g)
                if (!items.length) return null
                return (
                  <div key={g}>
                    <Text size="xs" c="dimmed" tt="uppercase" fw={600} px="sm" pt="sm" pb={4}>
                      {g}
                    </Text>
                    {items.map((t) => (
                      <NavLink
                        key={t.id}
                        label={t.title}
                        active={!words.length && t.id === current.id}
                        onClick={() => {
                          setQ('')
                          nav(`/help/${t.id}`)
                        }}
                        rightSection={t.admin ? <Badge size="xs" variant="light" color="gray">admin</Badge> : undefined}
                        style={{ borderRadius: 6 }}
                      />
                    ))}
                  </div>
                )
              })}
            </ScrollArea.Autosize>
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 9 }}>
          {words.length ? (
            <Card withBorder>
              <Title order={4} mb="sm">
                {results.length ? `${results.length} topic${results.length === 1 ? ' mentions' : 's mention'} “${q.trim()}”` : `Nothing found for “${q.trim()}”`}
              </Title>
              <Stack gap="md">
                {results.map((t) => (
                  <div key={t.id}>
                    <Anchor component={Link} to={`/help/${t.id}`} fw={600} onClick={() => setQ('')}>
                      {t.title}
                    </Anchor>
                    <Text size="xs" c="dimmed">
                      {t.group}
                    </Text>
                    <Text size="sm">{snippet(t, words)}</Text>
                  </div>
                ))}
                {!results.length && (
                  <Text size="sm" c="dimmed">
                    Try fewer or other words, or browse the topics on the left.
                  </Text>
                )}
              </Stack>
            </Card>
          ) : (
            <Card withBorder p="lg" maw={920}>
              <Group gap="xs" mb={4}>
                <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
                  {current.group}
                </Text>
                {current.admin && (
                  <Badge size="xs" variant="light" color="gray">
                    administrators
                  </Badge>
                )}
              </Group>
              <Title order={2}>{current.title}</Title>
              <Text c="dimmed" mb="sm">
                {current.summary}
              </Text>
              <Markdown source={current.body} />
              <Group justify="space-between" mt="xl" pt="md" style={{ borderTop: '1px solid var(--mantine-color-default-border)' }}>
                {prev ? (
                  <Anchor component={Link} to={`/help/${prev.id}`} size="sm">
                    <Group gap={4}>
                      <IconArrowLeft size={14} />
                      {prev.title}
                    </Group>
                  </Anchor>
                ) : (
                  <span />
                )}
                {next && (
                  <Anchor component={Link} to={`/help/${next.id}`} size="sm">
                    <Group gap={4}>
                      {next.title}
                      <IconArrowRight size={14} />
                    </Group>
                  </Anchor>
                )}
              </Group>
            </Card>
          )}
        </Grid.Col>
      </Grid>
    </>
  )
}
