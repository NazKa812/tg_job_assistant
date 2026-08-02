import asyncio
import os
import streamlit as st
from core.ai_engine import AIEngine
from core.telegram_worker import TelegramWorker
from config import DATA_DIR

# Настройка страницы Streamlit
st.set_page_config(
    page_title="Telegram Job AI Assistant",
    page_icon="🤖",
    layout="wide"
)

# Инициализация хранилища сессии Streamlit
if "base_resume_text" not in st.session_state:
    st.session_state.base_resume_text = ""
if "found_vacancies" not in st.session_state:
    st.session_state.found_vacancies = []

st.title("🤖 AI-Ассистент по поиску вакансий в Telegram")

tab_resume, tab_settings, tab_scan, tab_results = st.tabs([
    "📄 1. Резюме и Инструкция",
    "⚙️ 2. Фильтры и Каналы",
    "🔍 3. Сканирование",
    "✉️ 4. Вакансии и Отклики"
])

# -----------------------------------------------------------------------------
# Вкладка 1: Загрузка резюме и настройки промпта
# -----------------------------------------------------------------------------
with tab_resume:
    st.header("1. Загрузка вашего базового резюме")
    uploaded_file = st.file_uploader("Загрузите резюме в формате PDF", type=["pdf"])

    if uploaded_file:
        original_filename = uploaded_file.name
        # Сохраняем файл резюме в папку data/
        file_path = os.path.join(DATA_DIR, original_filename)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        st.session_state.resume_file_path = file_path
        st.session_state.resume_file_name = original_filename

        ai = AIEngine()
        resume_text = ai.extract_text_from_pdf(uploaded_file)
        st.session_state.base_resume_text = resume_text

        st.success(f"Резюме «{original_filename}» успешно загружено и сохранено в /data!")

        with st.expander("Посмотреть извлеченный текст резюме"):
            st.text_area("Текст резюме", resume_text, height=200, disabled=True)

    st.subheader("2. Пожелания к сопроводительному письму (Промпт)")
    custom_prompt = st.text_area(
        "Укажите правила и акценты для ИИ при написании писем:",
        value="Составь краткое, емкое сопроводительное письмо (до 500 символов). "
              "Подчеркни релевантный опыт и ключевые навыки под эту вакансию. "
              "Пиши без клише и без скобок.",
        height=100
    )

# -----------------------------------------------------------------------------
# Вкладка 2: Фильтры поиска и Telegram-каналы
# -----------------------------------------------------------------------------
with tab_settings:
    st.header("Настройка критериев поиска")

    keywords_input = st.text_input(
        "Ключевые слова для поиска вакансий (через запятую):",
        value="Python, QA, Automation, SQL, Тестирование"
    )
    keywords = [k.strip() for k in keywords_input.split(",") if k.strip()]

    st.subheader("Список Telegram-каналов")
    channels_input = st.text_area(
        "Введите ссылки или юзернеймы каналов (по одному на строку):",
        value="https://t.me/rabotadlaqa\nhttps://t.me/qajobsru\nhttps://t.me/qajobsoffers",
        height=150
    )
    channels_list = [c.strip() for c in channels_input.split("\n") if c.strip()]

# -----------------------------------------------------------------------------
# Вкладка 3: Сканирование каналов
# -----------------------------------------------------------------------------
with tab_scan:
    st.header("Мониторинг Telegram-каналов")
    st.write(
        "Нажмите кнопку, чтобы проверить каналы на наличие новых вакансий. Подходящие варианты мгновенно появятся в 4-м разделе.")

    limit_per_channel = st.slider("Глубина разовой проверки (постов на канал):", 3, 20, 5)

    if st.button("⚡ Проверить новые посты в каналах", type="primary", use_container_width=True):
        channels_to_scan = st.session_state.get("channels_list", [])

        if not st.session_state.base_resume_text:
            st.warning("⚠️ Сначала загрузите резюме на вкладке №1!")
        elif not channels_to_scan:
            st.warning("⚠️ Укажите каналы на вкладке №2!")
        else:
            ai = AIEngine()
            worker = TelegramWorker()

            with st.status("🔍 Опрос каналов и анализ ИИ...", expanded=True) as status:
                async def run_live_check():
                    await worker.init_client()

                    # Получаем уже существующие ID в памяти, чтобы не дублировать
                    existing_ids = {v["id"] for v in st.session_state.found_vacancies}
                    all_found = list(st.session_state.found_vacancies)
                    new_added_count = 0

                    for channel in channels_to_scan:
                        status.update(label=f"📂 Проверяем канал: {channel}...")
                        posts = await worker.fetch_channel_posts(channel, limit=limit_per_channel)

                        stop_words = [
                            "ищу работу", "ищу проект", "open to work", "резюме", "нахожусь в поиске",
                            "ищу позицию", "полезные телеграм-каналы", "мемы", "чаты:"
                        ]

                        for post in posts:
                            if post["id"] in existing_ids:
                                continue  # Уже есть в базе

                            text_lower = post["text"].lower()
                            if any(sw in text_lower for sw in stop_words):
                                continue

                            # Проверяем по ключевым словам
                            if ai.match_job_by_keywords(post["text"], keywords):
                                status.update(label=f"🤖 Найдена вакансия! Генерация письма через ИИ...")

                                # Генерируем письмо под эту вакансию
                                letter = ai.generate_cover_letter(
                                    st.session_state.base_resume_text,
                                    post["text"],
                                    custom_prompt
                                )
                                post["cover_letter"] = letter

                                # Сразу добавляем в начало списка найденных
                                all_found.insert(0, post)
                                existing_ids.add(post["id"])
                                new_added_count += 1
                                await asyncio.sleep(2)

                    await worker.close()
                    return all_found, new_added_count


                try:
                    updated_vacancies, added_count = asyncio.run(run_live_check())
                    st.session_state.found_vacancies = updated_vacancies
                    status.update(
                        label=f"✅ Готово! Новых вакансий добавлено в 4-й раздел: {added_count}",
                        state="complete"
                    )
                except Exception as e:
                    status.update(label=f"❌ Ошибка: {e}", state="error")

# -----------------------------------------------------------------------------
# Вкладка 4: Просмотр результатов и отправка
# -----------------------------------------------------------------------------
with tab_results:
    st.header("Найденные вакансии и авто-письма")

    if not st.session_state.found_vacancies:
        st.write("Пока нет найденных вакансий. Запустите сканирование на предыдущей вкладке.")
    else:
        for idx, vac in enumerate(st.session_state.found_vacancies):
            vac_id = vac.get('id', idx)
            channel_safe = vac.get('channel', 'channel').replace('@', '')
            prefix = f"v_{channel_safe}_{vac_id}_{idx}"

            with st.container():
                post_url = f"https://t.me/{channel_safe}/{vac_id}"

                st.subheader(f"Вакансия #{idx + 1} из канала @{vac['channel']}")
                st.markdown(f"[🔗 Открыть оригинал поста в Telegram]({post_url})")

                col1, col2 = st.columns([1, 1], gap="medium")

                with col1:
                    st.markdown("**Описание вакансии:**")
                    st.text_area(
                        "Текст поста",
                        vac.get("text", ""),
                        height=250,
                        key=f"txt_{prefix}",
                        disabled=True
                    )

                    hr_list = vac.get('contacts', [])
                    formatted_contacts = ", ".join(hr_list) if hr_list else "Не найдены"
                    st.write(f"**Найденные контакты HR:** {formatted_contacts}")

                with col2:
                    st.markdown("**Сгенерированное сопроводительное письмо:**")
                    edited_letter = st.text_area(
                        "Вы можете отредактировать письмо перед отправкой:",
                        vac.get("cover_letter", ""),
                        height=250,
                        key=f"let_{prefix}"
                    )

                    if hr_list:
                        selected_hr = st.selectbox(
                            "Выберите контакт для отправки:",
                            hr_list,
                            key=f"sel_{prefix}"
                        )

                        if st.button(f"✉️ Отправить отклик {selected_hr}", key=f"btn_{prefix}"):
                            worker = TelegramWorker()
                            resume_path = st.session_state.get("resume_file_path", None)
                            target_channel = vac.get('channel')
                            target_msg_id = vac.get('id')

                            async def send_msg():
                                success = await worker.send_application(
                                    hr_username=selected_hr,
                                    message_text=edited_letter,
                                    file_path=resume_path,
                                    channel=target_channel,
                                    message_id=target_msg_id
                                )
                                await worker.close()
                                return success

                            res = asyncio.run(send_msg())
                            if res:
                                filename_used = st.session_state.get("resume_file_name", "файлом")
                                st.success(f"Вакансия переслана, а сообщение и файл ({filename_used}) успешно отправлены для {selected_hr}!")
                            else:
                                st.error("Не удалось отправить сообщение. Проверьте логи.")
                    else:
                        st.warning("В посте не найдены контакты HR для автоматической отправки.")

                st.divider()