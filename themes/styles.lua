-- Pandoc Lua filter for the Typst (PDF) output.
-- Wraps each div/span carrying a custom-style attribute in #cv-style("name")[...]
-- so the theme file decides how the named style looks. Other formats pass through
-- unchanged (DOCX maps custom-style to Word styles natively).

local function opener(name)
  return '#cv-style("' .. name .. '")['
end

function Div(el)
  local name = el.attributes["custom-style"]
  if not name or not FORMAT:match("typst") then
    return nil
  end
  local blocks = { pandoc.RawBlock("typst", opener(name)) }
  for _, block in ipairs(el.content) do
    table.insert(blocks, block)
  end
  table.insert(blocks, pandoc.RawBlock("typst", "]"))
  return blocks
end

function Span(el)
  local name = el.attributes["custom-style"]
  if not name or not FORMAT:match("typst") then
    return nil
  end
  local inlines = { pandoc.RawInline("typst", opener(name)) }
  for _, inline in ipairs(el.content) do
    table.insert(inlines, inline)
  end
  table.insert(inlines, pandoc.RawInline("typst", "]"))
  return inlines
end
