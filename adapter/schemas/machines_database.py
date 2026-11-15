"""Response models for the machine-data database."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DatabaseMachine(BaseModel):
    """A machine from the secondary database's ``MASZYNY`` table."""

    id_tbl_maszyny: int | None = None
    id_maszyna: int | None = None
    id_klient: int | None = None
    id_nr_seryjny: str | None = None
    mac: str | None = None
    cpc: str | None = None
    marka: str | None = None
    model: str | None = None
    rodzaj_urzadzenia: str | None = None
    kolor: str | None = None
    licznik_calkowity: int | None = None
    licznik_mono: int | None = None
    licznik_kolor: int | None = None
    licznik_skan: int | None = None
    licznik_112: int | None = None
    licznik_113: int | None = None
    licznik_122: int | None = None
    licznik_123: int | None = None
    licznik_501: int | None = None
    licznik_kopia: int | None = None
    licznik_druk: int | None = None
    data_licznika: str | None = None
    przeglad_status: str | None = None
    przeglad_last_licz: int | None = None
    przeglad_next_licz: int | None = None
    przeglad_last_data: str | None = None
    przeglad_next_data: str | None = None
    przeglad_coile_licz: int | None = None
    przeglad_coile_data: int | None = None
    przeglad_wezwij: str | None = None
    przeglad_przydzielony: str | None = None
    przeglady_on_off: str | None = None
    miejsce_postoju: str | None = None
    email: str | None = None
    typ_toneru: str | None = None
    wersja_wtyczki: str | None = None
    notatki: str | None = None
    serwisant: str | None = None
    ip: str | None = None
    maska: str | None = None
    brama: str | None = None
    dns1: str | None = None
    dns2: str | None = None
    system: str | None = None
    dcon: str | None = None
    rcon: str | None = None
    rui: str | None = None
    opcje1: str | None = None
    opcje2: str | None = None
    opcje3: str | None = None
    opcje4: str | None = None
    opcje5: str | None = None
    opcje6: str | None = None
    opcje7: str | None = None
    opcje8: str | None = None
    opcje9: str | None = None
    opcje10: str | None = None
    panel_info1: str | None = None
    panel_info2: str | None = None
    panel_info3: str | None = None
    panel_info4: str | None = None
    belka_info: str | None = None
    serwisowana: str | None = None
    pokaz_kom_przeg: str | None = None
    przeg_po_licz: str | None = None
    przeg_po_dacie: str | None = None
    grupa: str | None = None
    lc_s: str | None = None
    lm_s: str | None = None
    lk_s: str | None = None
    ldr_s: str | None = None
    lko_s: str | None = None
    data_przydzielenia: str | None = None
    odswiez: int | None = None
    t_bk: str | None = None
    t_c: str | None = None
    t_m: str | None = None
    t_y: str | None = None
    t_bk_m: str | None = None
    t_c_m: str | None = None
    t_m_m: str | None = None
    t_y_m: str | None = None
    t_bk_n: str | None = None
    t_c_n: str | None = None
    t_m_n: str | None = None
    t_y_n: str | None = None
    b_bk: str | None = None
    b_c: str | None = None
    b_m: str | None = None
    b_y: str | None = None
    b_bk_m: str | None = None
    b_c_m: str | None = None
    b_m_m: str | None = None
    b_y_m: str | None = None
    b_bk_n: str | None = None
    b_c_n: str | None = None
    b_m_n: str | None = None
    b_y_n: str | None = None
    d_bk: str | None = None
    d_c: str | None = None
    d_m: str | None = None
    d_y: str | None = None
    d_bk_m: str | None = None
    d_c_m: str | None = None
    d_m_m: str | None = None
    d_y_m: str | None = None
    d_bk_n: str | None = None
    d_c_n: str | None = None
    d_m_n: str | None = None
    d_y_n: str | None = None
    poj_z_t: str | None = None
    poj_z_t_m: str | None = None
    poj_z_t_n: str | None = None
    fus: str | None = None
    fus_m: str | None = None
    fus_n: str | None = None
    mk: str | None = None
    mk_m: str | None = None
    mk_n: str | None = None
    tr: str | None = None
    tr_m: str | None = None
    tr_n: str | None = None
    plu: int | None = None
    pnu: int | None = None
    uwagi: str | None = None
    licz_m_ostatn_rozl: int | None = None
    licz_m_poprz_rozl: int | None = None
    licz_k_ostatn_rozl: int | None = None
    licz_k_poprz_rozl: int | None = None
    data_ostatn_rozl: str | None = None
    okres_ostatn_rozl: str | None = None
    data_instalacji: str | None = None
    data_stats: str | None = None
    zapas_bk: int | None = None
    zapas_c: int | None = None
    zapas_m: int | None = None
    zapas_y: int | None = None
    nr_inwentarzowy: str | None = None
    os_kosztow: str | None = None
    id_magazyn: int | None = None
    notatki_eksploatacja: str | None = None


class DatabaseMachinePage(BaseModel):
    """A page of secondary-database machine records."""

    total: int = Field(description="Total records matching search and filters")
    count: int = Field(description="Records in this page")
    limit: int
    offset: int
    machines: list[DatabaseMachine]
