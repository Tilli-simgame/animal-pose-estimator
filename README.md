# Hevosen rakenneanalyysi

Web-sovellus, joka arvioi hevosen rakenteen yhdestä sivukuvasta.

1. DeepLabCut SuperAnimal-Quadruped löytää hevosen ja osan anatomisista pisteistä;
   loput pisteet arvioidaan niistä (`src/horse_conformation/detect.py`).
2. Käyttäjä korjaa pisteet selaimessa raahaamalla.
3. Sääntömoottori laskee kulmat, mittasuhteet ja tasapainon ja vertaa niitä
   ihannealueisiin (`src/horse_conformation/rules.py`).

## Käynnistys

```
uv sync
uv run uvicorn horse_conformation.app:app --port 8000
```

Avaa http://localhost:8000. Ensimmäinen käynnistys lataa mallit (n. 200 Mt).
Älä käytä `--reload`-valitsinta: mallin vuoksi uudelleenlataus jää jumiin. Käynnistä
palvelin uudelleen Python-muutosten jälkeen (selainpuolen muutokset näkyvät pelkällä F5:llä).

## Julkaisu

Ks. [DEPLOY.md](DEPLOY.md) (Hetzner + Docker + Caddy/HTTPS).

## Käyttäjät

Palvelu vaatii kirjautumisen. Roolit: **ylläpitäjä** (käyttäjähallinta, voi muokata kaikkia
tallennuksia) ja **tuomari** (analyysi, tallennus aineistoon, omien tallennusten muokkaus).
Rekisteröitymistä ei ole – ylläpitäjä luo tunnukset sivulla `/users`.

Ensimmäinen ylläpitäjä luodaan komentoriviltä (kysyy salasanan):

```
uv run python -m horse_conformation.users create <tunnus> --admin --name "Näyttönimi"
uv run python -m horse_conformation.users reset-password <tunnus>   # hätätilanteisiin
uv run python -m horse_conformation.users list
```

Käyttäjät ja istunnot ovat tiedostossa `data/app.db`. HTTPS:n kanssa aseta `COOKIE_SECURE=1`.

## Kuvausohje

Hevonen suoraan sivulta, seisoo auki (kaikki neljä jalkaa näkyvissä), pää luonnollisessa
asennossa, kamera noin lavan korkeudella, tasainen maa.

## Aineisto

"Tallenna aineistoon" tallentaa kuvan (EXIF-tiedot poistettuna) kansioon `data/images/` ja
pisteet, hevosen tiedot (rotu, tyyppi, sukupuoli, ikä, IRL- ja URL-kantakirjatulos) sekä lasketut arviot
kansioon `data/annotations/`. Kansion voi vaihtaa ympäristömuuttujalla `HORSE_DATA_DIR`.
`data/` ei mene gitiin.

## Rakenne

| Tiedosto | Sisältö |
|---|---|
| `keypoints.py` | 24 pisteen määrittely (lähempi puoli) |
| `geometry.py` | Kuvan oikaisu maalinjan mukaan, kulmat |
| `rules.py` | Arviot, raja-arvot (`Range`) ja tulkinnat, kuvan laadun tarkistukset |
| `detect.py` | Mallin ajo ja SuperAnimal → oma pisteistö |
| `app.py`, `static/` | FastAPI + selainkäyttöliittymä |
| `spike/` | Ensimmäinen mallikokeilu |
| `samples/` | Testikuvat (Wikimedia Commons, ks. `SOURCES.md`) |
| `reference/` | Rakenteen viitekuvat |

Raja-arvot ovat alustavia, ja niitä kalibroidaan oikeiden arvioiden perusteella.

## Testit

```
uv run pytest
```
