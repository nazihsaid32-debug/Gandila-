import streamlit as st
import pandas as pd
from datetime import datetime, time
import plotly.express as px

# 1. Configuration de la page
st.set_page_config(page_title="AKHFENNIRE 1 - Advanced Manager", layout="wide")

# 2. Interface Principale (Header)
st.image("https://i1.hespress.com/wp-content/uploads/2020/02/energie___olienne_321369521.jpg", use_container_width=True)
st.markdown("<h1 style='text-align: center; color: #1E3A8A;'>Gestionnaire d'Alarmes AKHFENNIRE 1</h1>", unsafe_allow_html=True)
st.markdown("---")

# 3. Sidebar (Paramètres)
st.sidebar.header("🗓️ Sélection du Jour")
target_date = st.sidebar.date_input("Choisir le jour de travail", datetime.now())

st.sidebar.markdown("---")
st.sidebar.header("⚙️ Cas Spécial")
list_wtg = [f"WTG{str(i).zfill(2)}" for i in range(1, 62)]
selected_wtgs = st.sidebar.multiselect("Turbines impactées (Cas spécial)", list_wtg)
m_resp = st.sidebar.selectbox("Responsabilité (Cas spécial)", ["EEM", "GE", "ONEE", "Autres"])

# 4. Base Alarme (Priorités : 1=Haute / 2=Normale)
# Ajoutez ici vos codes d'alarme et la responsabilité associée
base_alarme = {
    '101': {'resp': 'EEM', 'pri': 1},
    '102': {'resp': 'WTG', 'pri': 1}, # Exemple Maintenance
    '103': {'resp': 'WTG', 'pri': 1}, # Exemple Manual Stop
}

# 5. Zone de téléchargement
uploaded_file = st.file_uploader("📂 Charger le fichier Excel des alarmes", type=["xlsx"])

if uploaded_file:
    try:
        # Recherche du début du tableau (Ligne contenant WTG0)
        raw_df = pd.read_excel(uploaded_file, header=None)
        header_row_index = None
        for i, row in raw_df.iterrows():
            if row.astype(str).str.contains('WTG0', case=False).any():
                header_row_index = i
                break
        
        if header_row_index is None:
            st.error("❌ Impossible de trouver la colonne 'WTG0'. Vérifiez le format du fichier.")
        else:
            # Chargement des données réelles
            df = pd.read_excel(uploaded_file, skiprows=header_row_index)
            # Nettoyage des noms de colonnes (espaces blancs)
            df.columns = [str(c).strip() for c in df.columns]

            # Noms exacts des colonnes fournis
            c_wtg = 'WTG0'
            c_code = 'Alarm code'
            c_text = 'Alarm text'
            c_start = 'Start Data And Time'
            c_end = 'End Date and Time'
            c_indisp = 'Indisponibilité H'

            # Conversion des dates
            df['S_DT'] = pd.to_datetime(df[c_start], dayfirst=True, errors='coerce')
            df['E_DT'] = pd.to_datetime(df[c_end], dayfirst=True, errors='coerce')
            
            # Limites du jour sélectionné
            d_start = datetime.combine(target_date, time(0, 0, 0))
            d_end = datetime.combine(target_date, time(23, 59, 59))
            
            # Filtrage et Ajustement (Clipping)
            df = df.dropna(subset=['S_DT', 'E_DT'])
            df = df[(df['S_DT'] <= d_end) & (df['E_DT'] >= d_start)].copy()
            df['S_DT'] = df['S_DT'].clip(lower=d_start)
            df['E_DT'] = df['E_DT'].clip(upper=d_end)
            
            processed_rows = []
            for wtg, group in df.groupby(c_wtg):
                group = group.sort_values(by=['S_DT'])
                for _, row in group.iterrows():
                    s, e = row['S_DT'], row['E_DT']
                    al_code, al_text = str(row[c_code]), str(row[c_text])
                    
                    # Déterminer la responsabilité
                    info = base_alarme.get(al_code, {'resp': 'WTG', 'pri': 2})
                    resp = m_resp if wtg in selected_wtgs else info['resp']
                    
                    # Logique de gestion des chevauchements et priorités
                    if not processed_rows or processed_rows[-1][0] != wtg:
                        processed_rows.append([wtg, al_code, al_text, s, e, resp, info['pri']])
                    else:
                        last_s, last_e, last_pri = processed_rows[-1][3], processed_rows[-1][4], processed_rows[-1][6]
                        
                        if s < last_e: # Chevauchement détecté
                            if info['pri'] < last_pri: # Nouvel événement prioritaire (EEM/Maintenance)
                                processed_rows[-1][4] = s
                                processed_rows.append([wtg, al_code, al_text, s, e, resp, info['pri']])
                            elif info['pri'] == last_pri: # Même priorité : Fusion du temps
                                processed_rows[-1][4] = max(last_e, e)
                            else: # Moins prioritaire : On complète après l'événement majeur
                                if e > last_e:
                                    processed_rows.append([wtg, al_code, al_text, last_e, e, resp, info['pri']])
                        else:
                            processed_rows.append([wtg, al_code, al_text, s, e, resp, info['pri']])

            # Création du tableau de résultats
            result_df = pd.DataFrame(processed_rows, columns=['WTG', 'Code', 'Alarme', 'Début', 'Fin', 'Responsabilité', 'Priority'])
            result_df['Durée_H'] = (result_df['Fin'] - result_df['Début']).dt.total_seconds() / 3600
            
            st.success(f"✅ Analyse terminée avec succès pour le {target_date}")
            st.dataframe(result_df.drop(columns=['Priority']))

            # --- Visualisations ---
            st.markdown("---")
            st.subheader("📊 Performance et Disponibilité")
            
            downtime = result_df.groupby('WTG')['Durée_H'].sum().reset_index()
            all_wtgs = pd.DataFrame({'WTG': [f"WTG{str(i).zfill(2)}" for i in range(1, 62)]})
            stats = pd.merge(all_wtgs, downtime, on='WTG', how='left').fillna(0)
            stats['Heures_Marche'] = 24 - stats['Durée_H']
            stats['Heures_Marche'] = stats['Heures_Marche'].clip(lower=0)

            fig = px.bar(stats, x='WTG', y='Heures_Marche', color='Heures_Marche', 
                         color_continuous_scale='RdYlGn', range_y=[0,24],
                         title="Heures de fonctionnement par turbine (Net sur 24h)")
            st.plotly_chart(fig, use_container_width=True)

            # Bouton d'exportation
            output_file = f"Rapport_Final_{target_date}.xlsx"
            result_df.to_excel(output_file, index=False)
            with open(output_file, "rb") as f:
                st.download_button("📥 Télécharger le Rapport Excel", f, file_name=output_file)

    except Exception as e:
        st.error(f"Une erreur est survenue lors de l'analyse : {e}")
