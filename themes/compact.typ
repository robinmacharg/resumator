// Compact preset: layered after default.typ to help a CV fit on fewer pages.
// Override only the cv-theme entries that change, then rebuild cv-style and re-apply cv-base.

#let cv-theme = cv-theme + (
  margin: 1.2cm,
  body-size: 8.5pt,
  name-size: 16pt,
  title-size: 11pt,
  contact-size: 9pt,
  section-size: 11pt,
  role-size: 9.5pt,
  summary-size: 9pt,
  requirements-heading-size: 8.5pt,
)

#let cv-style = cv-make-style(cv-theme)
#show: cv-base.with(cv-theme)
