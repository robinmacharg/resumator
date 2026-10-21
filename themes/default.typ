// Resumator default PDF theme.
//
// cv_convert emits semantic markup only: every styled element is a pandoc div/span
// with custom-style="<name>", which themes/styles.lua turns into #cv-style("<name>")[...].
// This file decides how each name looks. Unknown names render as plain body text.
//
// Presets (e.g. compact.typ) are included after this file: they override entries in
// cv-theme and then rebuild cv-style and re-apply cv-base (see compact.typ).

#let cv-theme = (
  margin: 1.5cm,
  body-size: 9pt,
  footer-size: 11pt,
  name-size: 18pt,
  title-size: 12pt,
  contact-size: 10pt,
  section-size: 12pt,
  role-size: 10pt,
  summary-size: 10pt,
  requirements-heading-size: 9pt,
  link-color: rgb("#0563C1"),
  bullet-gap: 0.45em,
)

// Page and body text. Applied as a show rule so presets can re-apply it.
#let cv-base(t, doc) = {
  set page(
    margin: t.margin,
    footer: context align(center, text(t.footer-size, counter(page).display("1"))),
  )
  set text(t.body-size)
  doc
}

// Web links are blue and underlined; mailto links stay plain text.
#let cv-link(t) = it => if type(it.dest) == str and it.dest.starts-with("mailto:") { it } else {
  underline(text(fill: t.link-color, it))
}

#let cv-centered(size) = body => align(center, text(size, weight: "bold", body))

#let cv-styles(t) = (
  candidate-name: cv-centered(t.name-size),
  candidate-title: cv-centered(t.title-size),
  candidate-contact: body => { show link: cv-link(t); cv-centered(t.contact-size)(body) },
  candidate-subheader: body => { show link: cv-link(t); cv-centered(t.contact-size)(body) },
  section-heading: body => text(t.section-size, weight: "bold", body),
  summary-item: body => text(t.summary-size, emph(body)),
  requirements-heading: body => text(t.requirements-heading-size, weight: "bold", body),
  // A markdown list, drawn as bullet/text rows so wrapped lines hang under the text.
  requirements-list: body => {
    show list: it => it.children.map(item => table(
      columns: (auto, 1fr),
      inset: 0pt,
      stroke: none,
      column-gutter: t.bullet-gap,
      [•], item.body,
    )).join()
    body
  },
  role-heading: body => text(t.role-size, weight: "bold", body),
  date-range: body => { show link: cv-link(t); body },
  keywords: body => body,
  education-title: body => strong(body),
  earlier-intro: body => body,
  earlier-title: body => strong(body),
  earlier-company: body => emph(body),
  skills-group: body => strong(body),
)

#let cv-make-style(t) = {
  let styles = cv-styles(t)
  (name, body) => styles.at(name, default: b => b)(body)
}

#let cv-style = cv-make-style(cv-theme)
#show: cv-base.with(cv-theme)
