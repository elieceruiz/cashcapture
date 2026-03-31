# app.py

import base64
from openai import OpenAI
import streamlit as st
from PIL import Image
from datetime import datetime
import os
from dotenv import load_dotenv
import re
import json
from collections import Counter
import requests
from pymongo import MongoClient
from io import BytesIO  # 👈 agrégalo arriba con los imports

# 🔥 importar util limpio
from cloudinary_upload import upload_image
from exif_reader import get_exif_datetime, get_datetime_from_filename


def get_payees():
    url = f"https://api.youneedabudget.com/v1/budgets/{os.getenv('YNAB_BUDGET_ID')}/payees"

    headers = {
        "Authorization": f"Bearer {os.getenv('YNAB_API_KEY')}"
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        data = response.json()
        return data["data"]["payees"]
    else:
        return []


def get_categories():
    url = f"https://api.youneedabudget.com/v1/budgets/{os.getenv('YNAB_BUDGET_ID')}/categories"

    headers = {
        "Authorization": f"Bearer {os.getenv('YNAB_API_KEY')}"
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        data = response.json()
        return data["data"]["category_groups"]
    else:
        return []


@st.cache_data
def load_payees():
    return get_payees()


@st.cache_data
def load_categories():
    return get_categories()


def flatten_categories(groups):
    categories = []
    for g in groups:
        for c in g["categories"]:
            if not c.get("deleted") and not c.get("hidden"):
                categories.append({
                    "name": c["name"],
                    "id": c["id"]
                })
    return categories


def clean_json_string(s):
    if s.startswith("```"):
        s = s.replace("```json", "").replace("```", "").strip()
    return s


load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 🔥 Mongo
mongo_client = MongoClient(os.getenv("MONGODB_URI"))
db = mongo_client[os.getenv("MONGODB_DB", "cashcapture")]
coleccion = db["aprendizaje"]


# 🔥 NUEVO (clave)
def normalize_payee(name):
    if not name:
        return ""
    return name.strip()

def get_aprendizaje(item, payee):
    if not item or not payee:
        return None
    return coleccion.find_one({"item": item, "payee": payee})

def get_aprendizaje_por_item(item):
    if not item:
        return None
    return coleccion.find_one({"item": item})

def save_aprendizaje(item, payee, category_name, precio):
    coleccion.update_one(
        {"item": item, "payee": payee},
        {            
            "$set": {
                "payee": payee,
                "category_name": category_name,
                "precio": precio
            },            
            "$inc": {"veces": 1}
        },
        upsert=True
    )

def normalize_item(name):
    if not name:
        return ""
    name = name.upper()
    basura = ["ENERGY DRINK", "DRINK", "BEBIDA", "ENERGIZANTE"]
    for b in basura:
        name = name.replace(b, "")
    return name.strip()

def analyze_image(file):
    file.seek(0)

    img = Image.open(file)
    img.thumbnail((800, 800))

    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=70)

    compressed_bytes = buffer.getvalue()

    base64_image = base64.b64encode(compressed_bytes).decode("utf-8")

    prompt = """ ... """

    with st.spinner("Analizando imagen..."):
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ],
                }
            ],
        )

    return response.choices[0].message.content

# UI
st.set_page_config(page_title="cashcapture", layout="centered")
st.title("📸 cashcapture")

file = st.file_uploader("Sube una foto", type=["jpg", "jpeg", "png"])

if file:
    img = Image.open(file)
    st.image(img, use_container_width=True)

    dt = get_exif_datetime(img) or get_datetime_from_filename(file.name)

    if dt:
        fecha = dt.strftime("%Y-%m-%d")
        hora = dt.strftime("%H:%M")
        st.success(f"{fecha} {hora}")
    else:
        now = datetime.now()
        fecha = now.strftime("%Y-%m-%d")
        hora = now.strftime("%H:%M")

    st.write("----")

    if st.button("Subir a Cloudinary"):
        filename = f"{fecha}_{hora.replace(':', '-')}"
        url = upload_image(file, filename)

        if url:
            st.success(url)
        else:
            st.error("Error subiendo imagen")

    if "result" not in st.session_state:
        st.session_state.result = None

    if st.button("Analizar imagen"):
        st.session_state.result = analyze_image(file)

    if st.session_state.result:
        try:
            cleaned = clean_json_string(st.session_state.result)
            data = json.loads(cleaned)

            opciones = data.get("opciones", [])

            items = [normalize_item(op.get("item")) for op in opciones if op.get("item")]
            conteo = Counter(items)

            items_unicos = list(conteo.keys()) + ["Manual"]

            fecha_input = st.date_input("Fecha", value=datetime.strptime(fecha, "%Y-%m-%d"))
            fecha = fecha_input.strftime("%Y-%m-%d")

            payees = [p for p in load_payees() if not p.get("deleted")]

            payee_map = {p["name"]: p["id"] for p in payees}
            payee_names = sorted(payee_map.keys())

            categories = flatten_categories(load_categories())
            category_map = {c["name"]: c["id"] for c in categories}
            category_names = sorted(category_map.keys())

            st.write("----")


            seleccion = st.radio("¿Qué registramos?", items_unicos)

            aprendizaje = None

            if seleccion == "Manual":
                item_raw = st.text_input("Item")
                item = normalize_item(item_raw)

                if item:
                    aprendizaje = get_aprendizaje_por_item(item)
                else:
                    aprendizaje = None

                cantidad = st.number_input("Cantidad", min_value=1, step=1)

                precio_default = 0
                if aprendizaje and aprendizaje.get("precio") is not None:
                    precio_default = int(aprendizaje["precio"])

            else:
                item = seleccion

                aprendizaje = get_aprendizaje_por_item(item)

                # st.write("ITEM →", repr(item))
                # st.write("MONGO RESULT →", aprendizaje)

                cantidad = st.number_input(
                    "Cantidad",
                    min_value=1,
                    value=conteo.get(seleccion, 1),
                    step=1
                )

                precio_detectado = next(
                    (op.get("precio") for op in opciones
                    if normalize_item(op.get("item")) == seleccion and op.get("precio")),
                    None
                )

                precio_default = 0

                if aprendizaje and aprendizaje.get("precio") is not None:
                    precio_default = int(aprendizaje["precio"])
                elif precio_detectado:
                    precio_default = int(precio_detectado)


            payee_options = ["-- Selecciona Payee --"] + payee_names

            default_payee_index = 0

            if aprendizaje and aprendizaje.get("payee"):
                for i, name in enumerate(payee_names):
                    if normalize_payee(name) == aprendizaje["payee"]:
                        default_payee_index = i + 1
                        break

            selected_payee = st.selectbox("Payee", payee_options, index=default_payee_index)

            if selected_payee == "-- Selecciona Payee --":
                payee_id = None
            else:
                payee_id = payee_map[selected_payee]

            # 🔥 APRENDIZAJE POR CONTEXTO
            payee_norm = normalize_payee(selected_payee) if payee_id else None
            aprendizaje_payee = get_aprendizaje(item, payee_norm) if payee_norm else None

            # 🔥 PRECIO FINAL (ANTES DEL INPUT)
            precio_default_final = precio_default

            if aprendizaje_payee and aprendizaje_payee.get("precio") is not None:
                precio_default_final = int(aprendizaje_payee["precio"])

            # 🔥 INPUT PRECIO (YA CORRECTO)
            precio = st.number_input(
                "Precio unitario",
                value=precio_default_final,
                step=100,
            )

            # 🔥 CATEGORY INDEX (BIEN HECHO)
            default_category_index = 0
            
            category_options = ["-- Selecciona Category --"] + category_names

            # calcular índice correcto
            if aprendizaje_payee and aprendizaje_payee.get("category_name"):
                try:
                    default_category_index = category_names.index(aprendizaje_payee["category_name"]) + 1
                except ValueError:
                    default_category_index = 0

            elif aprendizaje and aprendizaje.get("category_name"):
                try:
                    default_category_index  = category_names.index(aprendizaje["category_name"]) + 1
                except ValueError:
                    default_category_index = 0
            else:
                default_category_index = 0

            # 👇 ESTE ES EL QUE TE FALTA
            selected_category = st.selectbox(
                "Category",
                category_options,
                index=default_category_index
            )

            # mapear id
            if selected_category == "-- Selecciona Category --":
                category_id = None
            else:
                category_id = category_map[selected_category]

            total = cantidad * precio

            memo = f"{hora} {item}".strip().upper()

            if total == 0:
                st.warning("⚠️ El total no puede ser 0")

            st.write("----")
            st.write("🧾 Preview")
            st.write(f"Fecha: {fecha}")
            st.write(f"Payee: {selected_payee}")            
            st.write(f"Category: {selected_category}")
            st.write(f"Memo: {memo}")
            st.write(f"{cantidad} x {precio} = {total}")

            if st.button("Enviar a YNAB") and total > 0 and payee_id and category_id:
                url = f"https://api.youneedabudget.com/v1/budgets/{os.getenv('YNAB_BUDGET_ID')}/transactions"

                headers = {
                    "Authorization": f"Bearer {os.getenv('YNAB_API_KEY')}",
                    "Content-Type": "application/json"
                }

                data = {
                    "transaction": {
                        "account_id": os.getenv("YNAB_ACCOUNT_ID"),
                        "date": fecha,
                        "amount": -int(total * 1000),
                        "payee_id": payee_id,
                        "category_id": category_id,
                        "memo": memo,
                        "cleared": "cleared"
                    }
                }

                response = requests.post(url, headers=headers, json=data)

                if response.status_code == 201:
                    if item:  # 👈 SOLO guarda si hay item válido
                        payee_norm = normalize_payee(selected_payee)
                        save_aprendizaje(item, payee_norm, selected_category, precio)
                    st.success("✅ Enviado a YNAB")
                else:
                    st.error(response.text)

        except Exception as e:
            st.error("Error parseando JSON")
            st.text(str(e))
            st.code(st.session_state.result)