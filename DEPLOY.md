# Julkaisu

Palvelu ajetaan Dockerilla: sovellus + Caddy, joka hakee ja uusii HTTPS-sertifikaatin
automaattisesti. Koodi viedään palvelimelle skriptillä `scripts/deploy.ps1`, ja samalla
skriptillä julkaistaan myöhemmät päivitykset. Palvelimen `data/` (käyttäjät, kuvat,
tallennukset) ja `.env` eivät muutu päivityksissä.

Tarve: 2 ydintä ja 4 GB muistia riittää (mitattu: ~1 GB muistia, 2–3 s per kuva).
Docker-kuva toimii sekä x86- että Arm-palvelimilla.

- [Oracle Cloud Always Free](#oracle-cloud-always-free) (Arm, ilmainen)
- [Hetzner](#vaihtoehto-hetzner) (x86, n. 4–8 €/kk)

## SSH-avain (kerran, omalla koneella)

Tarkista PowerShellissä, onko avain jo olemassa:

```powershell
Get-Content $HOME\.ssh\id_ed25519.pub
```

Jos ei ole, luo se (Enter oletuksille, salasanan voit asettaa):

```powershell
ssh-keygen -t ed25519
```

---

## Oracle Cloud Always Free

### 1. Instanssi

*Compute → Instances → Create instance*:

| Valinta | Arvo |
|---|---|
| Image | **Canonical Ubuntu 24.04** (Change image → Ubuntu) |
| Shape | **Ampere VM.Standard.A1.Flex**. 2 OCPU / 12 GB riittää reilusti; voit käyttää myös koko 4 / 24 GB. |
| Networking | Julkinen aliverkko, **Assign a public IPv4 address** päällä |
| SSH keys | *Paste public keys*: tiedoston `id_ed25519.pub` sisältö |
| Boot volume | Oletus (n. 47 GB) riittää |

Kirjoita ylös instanssin **Public IP address**, esim. `158.180.1.2`.

### 2. Portit auki (Oraclen palomuuri)

*Instance → Subnet-linkki → Security Lists → Default Security List → Add Ingress Rules*,
lähde `0.0.0.0/0`:

| Protocol | Destination port |
|---|---|
| TCP | 80 |
| TCP | 443 |
| UDP | 443 |

### 3. Docker ja palvelimen oma palomuuri (kerran)

```powershell
ssh ubuntu@158.180.1.2
```

Palvelimella (Oraclen Ubuntu sallii oletuksena vain SSH:n, joten avataan 80 ja 443):

```bash
sudo apt update && sudo apt upgrade -y
curl -fsSL https://get.docker.com | sudo sh
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo iptables -I INPUT 6 -p udp --dport 443 -j ACCEPT
sudo netfilter-persistent save
exit
```

### 4. Osoite

- **Oma verkkotunnus:** DNS:ään A-tietue, esim. `rakenne.oma-domain.fi → 158.180.1.2`.
- **Ilman omaa verkkotunnusta:** ilmainen `sslip.io`-nimi, jossa IP on viivoilla:
  `158-180-1-2.sslip.io`. Toimii heti.

### 5. Ensimmäinen julkaisu

Projektikansiossa omalla koneella:

```powershell
.\scripts\deploy.ps1 -Server 158.180.1.2 -User ubuntu
```

Ensimmäisellä kerralla skripti pysähtyy, koska `.env` puuttuu. Aseta osoite:

```powershell
ssh -t ubuntu@158.180.1.2 "sudo nano /opt/rakenne/.env"
```

Kirjoita esim. `DOMAIN=158-180-1-2.sslip.io`, tallenna `Ctrl+O`, `Enter`, poistu `Ctrl+X`
ja aja skripti uudelleen. Ensimmäinen rakennus kestää 5–15 minuuttia.

### 6. Ylläpitäjätunnus

Palvelimen käyttäjät ovat erillisiä koneesi käyttäjistä:

```powershell
ssh -t ubuntu@158.180.1.2 "cd /opt/rakenne && sudo docker compose exec app uv run python -m horse_conformation.users create tilli --admin --name Tilli"
```

Avaa `https://<DOMAIN>` ja kirjaudu.

### Päivitykset

```powershell
.\scripts\deploy.ps1 -Server 158.180.1.2 -User ubuntu
```

### Varmuuskopio

```powershell
scp -r ubuntu@158.180.1.2:/opt/rakenne/data .\varmuuskopio-$(Get-Date -Format yyyy-MM-dd)
```

Lisäksi Oraclessa voi ottaa boot volumesta varmuuskopion
(*Block Storage → Boot Volumes → Boot Volume Backups*; Always Free sisältää 5 kpl).

### Huomioitavaa Oraclessa

- **Käyttämättömien instanssien palautus:** Oracle voi pysäyttää Always Free -instanssin,
  jos sen prosessorin, verkon ja muistin käyttö on 7 päivän ajan hyvin vähäistä. Tämä
  palvelu on suurimman osan ajasta joutilaana. Varmin tapa välttää pysäytys on muuttaa tili
  **Pay As You Go** -tiliksi: Always Free -resurssit pysyvät ilmaisina, eikä palautussääntö
  koske niitä. Aseta samalla budjettihälytys (esim. 1 €), niin huomaat heti, jos jokin
  alkaa maksaa.
- Instanssin julkinen IP pysyy samana niin kauan kuin instanssia ei poisteta.

---

## Vaihtoehto: Hetzner

Kuten yllä, mutta:

1. *Hetzner Cloud Console → Add Server*: Location **Helsinki**, Image **Ubuntu 24.04**,
   Shared vCPU **2 vCPU / 4 GB** (esim. CX23, CX22, CPX21 tai Arm-malli CAX11),
   SSH-avain, palomuuri (sisään TCP 22, 80, 443 ja UDP 443), **Backups** päälle.
2. Kirjautuminen on `root`-käyttäjänä eikä palvelimen omaa palomuuria tarvitse avata:
   ```bash
   ssh root@95.217.1.2
   apt update && apt upgrade -y
   curl -fsSL https://get.docker.com | sh
   ```
3. Julkaisu ja päivitykset: `.\scripts\deploy.ps1 -Server 95.217.1.2`
4. `.env`: `ssh -t root@95.217.1.2 "nano /opt/rakenne/.env"`
5. Ylläpitäjä: `ssh -t root@95.217.1.2 "cd /opt/rakenne && docker compose exec app uv run python -m horse_conformation.users create tilli --admin --name Tilli"`

---

## Vianetsintä

```bash
cd /opt/rakenne
sudo docker compose ps                 # ovatko palvelut käynnissä
sudo docker compose logs -f app        # sovelluksen loki
sudo docker compose logs caddy         # HTTPS-sertifikaatin haku
sudo docker compose restart app        # uudelleenkäynnistys
```

- **Sertifikaatti ei tule / sivu ei aukea:** tarkista, että DNS osoittaa palvelimen IP:hen
  ja että portit 80 ja 443 ovat auki (Oraclessa sekä Security List että iptables).
- **Unohtunut salasana:**
  `sudo docker compose exec app uv run python -m horse_conformation.users reset-password <tunnus>`
