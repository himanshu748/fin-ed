const OFFICIAL_SOURCE_TITLES = new Map<string, string>([
  [
    'https://www.incometaxindia.gov.in/documents/d/guest/income_tax_act_2025_as_amended_by_fa_act_2026-pdf',
    'Income-tax Act, 2025 as amended by Finance Act, 2026',
  ],
  [
    'https://www.incometax.gov.in/iec/foportal/help/all-topics/e-filing-services/General%20Questions-faqs?mobile-app=1',
    'Income Tax Department transition FAQ',
  ],
  [
    'https://www.cbic.gov.in/resources//htdocs-cbec/gst/central-tax-rate/01-2017-ctr-eng.pdf',
    'CBIC Notification No. 1/2017-Central Tax (Rate), Schedule V',
  ],
  [
    'https://www.nseindia.com/static/products-services/equity-derivatives-securities-transaction-tax',
    'NSE Securities Transaction Tax rates',
  ],
]);

function relabelOfficialSource(message: string, url: string, title: string): string {
  const titledLink = `[${title}](${url})`;
  let result = message
    .replaceAll(`([${url}](${url}))`, titledLink)
    .replaceAll(`[${url}](${url})`, titledLink);

  let searchFrom = 0;
  while (searchFrom < result.length) {
    const index = result.indexOf(url, searchFrom);
    if (index === -1) break;

    if (result.slice(Math.max(0, index - 2), index) === '](') {
      searchFrom = index + url.length;
      continue;
    }

    result = `${result.slice(0, index)}${titledLink}${result.slice(index + url.length)}`;
    searchFrom = index + titledLink.length;
  }

  return result.replaceAll(`(${titledLink})`, titledLink);
}

export function formatOfficialSourceLinks(message: string): string {
  let formatted = message;
  for (const [url, title] of OFFICIAL_SOURCE_TITLES) {
    formatted = relabelOfficialSource(formatted, url, title);
  }
  return formatted;
}
