from sqlalchemy import create_engine
from dotenv import load_dotenv, dotenv_values
from sqlalchemy.orm import sessionmaker
from utils import PROJ_ROOT_PATH
from WB_parser import uruchom_raport_dla_miesiaca
import sys

def main():
    env_path = PROJ_ROOT_PATH / '.env'
    load_dotenv(env_path)

    env_values = dotenv_values(env_path)
    if "" in env_values.values():
        print("Not all environmental variables were set in .env file.")

    argv = sys.argv
    if len(argv) < 5:
        print("Użycie: python main.py <YYYYMM> <sciezka_plik_naglowki> <sciezka_plik_pozycje> <NIP>")

    miesiac = argv[1]
    plik_naglowek = argv[2]
    plik_pozycje = argv[3]
    NIP = argv[4]

    try:
        db_user = env_values['DB_USER']
        db_address = env_values['DB_ADDRESS']
        db_name = env_values['DB_NAME']
        db_password = env_values['DB_PASSWORD']
    except KeyError as e:
        print("Not all environmental variables were written to .env file", e)
        return

    conn_addr = f"mssql+pyodbc://{db_user}:{db_password}@{db_address}/{db_name}?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
    engine = create_engine(conn_addr, connect_args={'timeout': 5})

    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as db_session:
        uruchom_raport_dla_miesiaca(db_session, NIP, miesiac, plik_naglowek, plik_pozycje)


if __name__ == "__main__":
    main()
