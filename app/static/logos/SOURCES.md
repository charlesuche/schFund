# Provider logos

How to add a logo, once the provider's own brand or press page allows it
(several require permission first):

1. Save the file here, small and optimised (under 30 KB), named after the
   provider key in `app/providers.py`: `nawa.svg`, `daad.svg`, ...
   (`.svg`, `.png`, `.webp` or `.jpg`).
2. In each of that provider's records, set
   `"provider_logo": {"file": "nawa.svg", "source_url": "<brand page>", "added_on": "YYYY-MM-DD"}`.
   Records without it show the provider's initials.
3. Add a row to the table below. `python scripts/validate.py` fails if a
   record names a file that is not here.

| File | Provider | Source page | Permission / terms | Added |
|---|---|---|---|---|

No files added yet: as of 2026-10-28 no provider publishes terms that allow
a third-party site to use its logo without asking first. The table below records
what each provider's own pages say, so a logo can be added once permission is given.

## Checked 2026-10-28: not added

"Public download, no terms" means the logo can be downloaded but the page does not
say who may use it. Those are the easiest to ask for.

| Key | Provider | Where checked | What it says | Ask |
|---|---|---|---|---|
| turkiye-burslari | Türkiye Scholarships | https://www.turkiyeburslari.gov.tr/about/mediaandpresentation/logo | Public download (PDF/JPG/PNG), no terms | Via site contact |
| nawa | NAWA | https://nawa.gov.pl/promocja-i-targi/materialy-do-pobrania/materialy-w-jezyku-angielskim | Public Logo.zip, no terms | https://nawa.gov.pl/kontakt |
| chalmers | Chalmers | https://www.chalmers.se/en/current/press-and-media/ | Media bank offers logos; no terms; logo may not be altered | Chalmers press office |
| daad | DAAD | DAAD corporate design pages | Use needs DAAD's consent | corporate-design@daad.de |
| chevening | Chevening | Chevening brand guidance | Explicit approval required | Chevening secretariat |
| gates-cambridge | Gates Cambridge | Gates Cambridge press page | Logo on request only | news@gatescambridge.org |
| csc | Commonwealth Scholarship Commission | CSC brand pages | For partners and alumni only | CSC communications |
| rhodes | Rhodes Trust | Rhodes Trust site | No terms published | Rhodes Trust communications |
| knight-hennessy | Knight-Hennessy Scholars | KHS site | No terms or files published | KHS communications |
| kth | KTH | KTH graphic profile | External parties need written consent | grafiskprofil@kth.se |
| lund | Lund University | Lund graphic profile | For the university's own use | grafiskprofil@kommunikation.lu.se |
| uppsala | Uppsala University | Uppsala graphic profile | For the university and its partners | Uppsala communications |
| si | Swedish Institute | SI press page | No logo policy | presse@si.se |
| glasgow | University of Glasgow | Glasgow brand pages | Brand team only | brand@glasgow.ac.uk |
| strathclyde | University of Strathclyde | Strathclyde brand pages | No terms for external use | Strathclyde brand team |
| leeds | University of Leeds | Leeds brand pages | Advance permission required | Leeds Creative team |
| warwick | WMG, University of Warwick | Warwick brand pages | Express Brand Team permission | brand@warwick.ac.uk |
| aston | Aston University | Aston brand pages | Written approval required | brandapproval@aston.ac.uk |
| maastricht | Maastricht University | UM house style pages | No third-party use without prior consent | UM House Style Office |
| fao | FAO | https://www.fao.org/contact-us/terms/en/ | Prohibited without prior written permission, including next to links to FAO | Address on the terms page |
| hec | HEC Paris | https://www.hec.edu/en/school/newsroom | No logo terms found | HEC communications |
| stellenbosch | Stellenbosch University | https://blogs.sun.ac.za/ccmd/ | Trademark Office handles use of SU marks | trademark@sun.ac.za |
| polito | Politecnico di Torino | https://www.polito.it/en/polito/about-us/corporate-image | Any use authorised by the university (Rector) | Online form, Ufficio Promozione Immagine |
| unipd | University of Padova | https://www.unipd.it/patrocini-uso-marchio | Use granted by the Communication Office | comunicazione@unipd.it |
| unipv | University of Pavia | https://portale.unipv.it/it/brand-identity | Written request to the Rector | Servizio Comunicazione |
| unisi | University of Siena | https://www.unisi.it/ateneo/richiesta-uso-logo | Request to the Rector; answer within 15 days | Rector's email/PEC |
| univr | University of Verona | https://www.univr.it/en/our-services/services-for-companies-and-organisations/becoming-a-sponsor-of-the-university-of-verona-and-requests-to-use-the-logo | Rector's approval; form Allegato B | Area Comunicazione |
| unica | University of Cagliari | https://www.unica.it/it/ateneo/chi-siamo/identita-visiva | Third parties need a licence or patronage | UniCA communications |
| unical | University of Calabria | https://www.unical.it/identita-visiva-di-ateneo/ | Licence needs Board approval | UniCal communications |
| unime | University of Messina | https://www.unime.it/sites/default/files/2023-03/Regolamento%20marchio%20e%20altri%20segni%20distintivi%20e%20conc.%20patrocinio.pdf | Licence by written contract | Request to the Rector |
| unimore | University of Modena and Reggio Emilia | https://www.unimore.it/it/ateneo/statuto-e-regolamenti/normativa-generale | Prior authorisation by the Board or Rector | Unimore Communication Area |
| maeci | Italian Ministry of Foreign Affairs | https://www.esteri.it | No terms found | MAECI press office |
| romania-mfa | Romanian Ministry of Foreign Affairs | https://www.mae.ro/en/node/4149 | Visual identity manual exists; terms not published | MFA press office |
| stipendium-hungaricum | Stipendium Hungaricum | https://stipendiumhungaricum.hu/ | No logo page or terms found | Tempus Public Foundation |
| dsu-toscana | DSU Toscana | https://www.dsu.toscana.it | No logo terms found | DSU Toscana communications |
| edisu-pavia | EDiSU Pavia | Official site | No logo terms found | EDiSU Pavia |
| edisu-piemonte | EDISU Piemonte | Official site | No logo terms found | EDISU Piemonte |
| ergo | ER.GO | Official site | No logo terms found | ER.GO |
| ersu-messina | ERSU Messina | Official site | No logo terms found | ERSU Messina |
| esu-padova | ESU Padova | Official site | No logo terms found | ESU Padova |
| disco | DiSCo Lazio | Official site | No logo terms found | DiSCo Lazio |
| intermaths | InterMaths | https://www.intermaths.eu | No logo terms found | InterMaths consortium office |
| boustany | Boustany Foundation | Official site | No logo terms found | Boustany Foundation |
