import { Alert, Anchor, Box, Code, List, Table, Text, Title } from '@mantine/core'
import { IconBulb } from '@tabler/icons-react'
import { Fragment, type ReactNode } from 'react'
import { Link } from 'react-router-dom'

/**
 * Just enough Markdown for the help topics, rendered as React elements (no HTML injection):
 * ## and ### headings, paragraphs, - and 1. lists, > tips, ``` code blocks, | tables |,
 * and inline **bold**, *italic*, `code` and [links](/page) / [links](help:topic) / [links](https://…).
 */
export function Markdown({ source }: { source: string }) {
  const lines = source.replace(/^\n+|\s+$/g, '').split('\n')
  const out: ReactNode[] = []
  let i = 0
  const key = () => out.length
  while (i < lines.length) {
    const line = lines[i]
    if (!line.trim()) {
      i++
    } else if (line.startsWith('```')) {
      const code: string[] = []
      i++
      while (i < lines.length && !lines[i].startsWith('```')) code.push(lines[i++])
      i++
      out.push(
        <Code key={key()} block my="sm" style={{ whiteSpace: 'pre', overflowX: 'auto', fontSize: 12.5 }}>
          {code.join('\n')}
        </Code>,
      )
    } else if (/^#{2,3} /.test(line)) {
      const level = line.startsWith('### ') ? 5 : 4
      out.push(
        <Title key={key()} order={level} mt="lg" mb={6}>
          {inline(line.replace(/^#+ /, ''))}
        </Title>,
      )
      i++
    } else if (line.startsWith('> ')) {
      const text: string[] = []
      while (i < lines.length && lines[i].startsWith('> ')) text.push(lines[i++].slice(2))
      out.push(
        <Alert key={key()} my="sm" variant="light" color="violet" icon={<IconBulb size={18} />}>
          <Text size="sm">{inline(text.join(' '))}</Text>
        </Alert>,
      )
    } else if (line.startsWith('|')) {
      const rows: string[][] = []
      while (i < lines.length && lines[i].startsWith('|')) {
        const cells = lines[i++].replace(/^\||\|$/g, '').split('|').map((c) => c.trim())
        if (!cells.every((c) => /^:?-+:?$/.test(c))) rows.push(cells)
      }
      const [head, ...body] = rows
      out.push(
        <Table.ScrollContainer key={key()} minWidth={480} my="sm">
          <Table withTableBorder withColumnBorders fz="sm" verticalSpacing={6}>
            <Table.Thead>
              <Table.Tr>
                {head.map((c, j) => (
                  <Table.Th key={j}>{inline(c)}</Table.Th>
                ))}
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {body.map((r, n) => (
                <Table.Tr key={n}>
                  {r.map((c, j) => (
                    <Table.Td key={j}>{inline(c)}</Table.Td>
                  ))}
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>,
      )
    } else if (/^(- |\d+\. )/.test(line)) {
      const ordered = /^\d+\. /.test(line)
      const items: { text: string; sub: string[] }[] = []
      while (i < lines.length && (/^(- |\d+\. )/.test(lines[i]) || /^ {2,}\S/.test(lines[i]))) {
        if (/^ {2,}- /.test(lines[i])) items[items.length - 1]?.sub.push(lines[i].trim().slice(2))
        else if (/^ {2,}\S/.test(lines[i]) && items.length) items[items.length - 1].text += ' ' + lines[i].trim()
        else items.push({ text: lines[i].replace(/^(- |\d+\. )/, ''), sub: [] })
        i++
      }
      out.push(
        <List key={key()} type={ordered ? 'ordered' : 'unordered'} size="sm" spacing={4} my="xs" withPadding>
          {items.map((it, n) => (
            <List.Item key={n}>
              {inline(it.text)}
              {it.sub.length > 0 && (
                <List size="sm" spacing={2} withPadding mt={2}>
                  {it.sub.map((s, m) => (
                    <List.Item key={m}>{inline(s)}</List.Item>
                  ))}
                </List>
              )}
            </List.Item>
          ))}
        </List>,
      )
    } else {
      const para: string[] = []
      while (i < lines.length && lines[i].trim() && !/^(```|#{2,3} |> |\||- |\d+\. )/.test(lines[i])) para.push(lines[i++])
      out.push(
        <Text key={key()} size="sm" my="xs" lh={1.6}>
          {inline(para.join(' '))}
        </Text>,
      )
    }
  }
  return <Box>{out}</Box>
}

const TOKEN = /(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|`[^`]+`|\[[^\]]+\]\([^)\s]+\))/g

/** Inline formatting: bold, italic, code and links. */
export function inline(text: string): ReactNode {
  const parts = text.split(TOKEN)
  return parts.map((p, n) => {
    if (!p) return null
    if (p.startsWith('**') && p.endsWith('**')) return <strong key={n}>{inline(p.slice(2, -2))}</strong>
    if (p.startsWith('`') && p.endsWith('`')) return <Code key={n}>{p.slice(1, -1)}</Code>
    if (p.startsWith('*') && p.endsWith('*') && p.length > 2) return <em key={n}>{inline(p.slice(1, -1))}</em>
    const link = /^\[([^\]]+)\]\(([^)\s]+)\)$/.exec(p)
    if (link) {
      const [, label, href] = link
      if (href.startsWith('help:'))
        return (
          <Anchor key={n} component={Link} to={`/help/${href.slice(5)}`} size="sm">
            {inline(label)}
          </Anchor>
        )
      if (href.startsWith('/') && !href.startsWith('/api/'))
        return (
          <Anchor key={n} component={Link} to={href} size="sm">
            {inline(label)}
          </Anchor>
        )
      return (
        <Anchor key={n} href={href} target="_blank" rel="noreferrer" size="sm">
          {inline(label)}
        </Anchor>
      )
    }
    return <Fragment key={n}>{p}</Fragment>
  })
}

/** Plain text of a topic, for search and result snippets. */
export function plain(source: string): string {
  return source
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/^\s*(- |\d+\. |#+ |> )/gm, '')
    .replace(/^\|?[\s|:-]+\|?$/gm, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/[*`|]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}
