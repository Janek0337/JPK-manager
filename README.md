# JPK-manager

Narzędzie do generowania plików XML wyciągów bankowych, zgodnych z wymaganiami Ministerstwa Finansów.

# Przed użyciem
Narzędzie zakłada możliwość dostępu do bazy danych (oryginalnie tworzone dla bazy typu MS-SQL).
Należy uzupełnić plik `.env.example` o odpowiednie dane autoryzacyjne i zmienić nazwę pliku na `.env`

# Użycie
Zakładając, że użytkownik ma ściągnięte narzędzie uv:

- `git clone https://github.com/Janek0337/JPK-manager`
- `cd JPK-manager`
- 'uv sync'
- `source ./.venv/bin/activate`
- `uv run python3 src/main.py <YYYYMM> <plik_z_nagłówkami> <plik_z_pozycjami> <IBAN>`