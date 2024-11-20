from flask import Flask, render_template, request, redirect, url_for
import pandas as pd
import re
import os

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'csv'}
app.debug = True

@app.route('/billing', methods=['GET', 'POST'])
def billing():
    if request.method == 'POST':
        telephony_file = request.files.get('telephony_file')
        sms_file = request.files.get('sms_file')  # Fixed issue by adding sms_file handling
        robot_file = request.files.get('robot_file')

        telephony_data, sms_data, robot_data = None, None, None
        if telephony_file and allowed_file(telephony_file.filename):
            telephony_data = pd.read_csv(telephony_file)
        if sms_file and allowed_file(sms_file.filename):
            sms_data = pd.read_csv(sms_file)
        if robot_file and allowed_file(robot_file.filename):
            robot_data = pd.read_csv(robot_file)

        telephony_result = analyze_telephony(telephony_data) if telephony_data is not None else None
        sms_result = analyze_sms(sms_data) if sms_data is not None else None
        robot_result = analyze_robot(robot_data) if robot_data is not None else None

        return render_template('billing.html',
                               telephony_result=telephony_result,
                               sms_result=sms_result,
                               robot_result=robot_result)
    
    return render_template('billing.html')

def analyze_telephony(df):
    # Очистка данных
    df.columns = df.columns.str.strip()  # Удаляем пробелы в названиях столбцов
    df['Sip id'] = df['Sip id'].astype(str).str.strip()  # Преобразуем в строки и удаляем пробелы
    df['Sip id'] = df['Sip id'].str.replace("Parameter:", "", regex=False)  # Удаляем текст "Parameter:"
    df.rename(columns={"Numberofservicesteps": "Number of steps"}, inplace=True)
    
    # Ключевые слова для поиска кампаний
    campaign_keywords = ["Pocket", "ExNova", "Exnova", "Mayan", "Betboom"]

    grouped_data = []
    campaign_name = None  # Для хранения текущей кампании
    
    for _, row in df.iterrows():
        sip_id = row['Sip id']

        # Проверяем, содержит ли строка одно из ключевых слов
        if any(keyword in sip_id for keyword in campaign_keywords):
            campaign_name = sip_id  # Устанавливаем название кампании
            continue

        # Если это данные провайдера и они валидные
        if campaign_name and pd.notna(sip_id) and sip_id not in ["", "nan", "By tariff type: Per 30 second"]:
            # Пропускаем провайдеров с "exnova" и "Per second" (игнорируем)
            if "exnova" in sip_id.lower() or "per second" in sip_id.lower():
                continue
            
            # Добавляем информацию о провайдере
            grouped_data.append({
                'campaign': campaign_name,  # Название кампании
                'provider': sip_id,  # Название провайдера
                'total_steps': row['Number of steps']  # Шаги сервиса
            })

    return grouped_data




def analyze_sms(df):
    # Фильтруем строки, где есть слово "Согласие"
    filtered_df = df[df['Business process action'].str.contains('Согласие', case=False, na=False)]
    grouped = filtered_df.groupby('Business process action').sum()
    return grouped[['Count of paid SMS', 'Number of SMS with commission']].to_dict(orient='index')

def analyze_robot(df):
    # Суммируем Number of service steps по кампаниям
    grouped = df.groupby('Sip id').sum()
    return grouped[['Number of service steps']].to_dict(orient='index')

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def filter_by_branch(df, branch):
    return df[df['Action'].str.contains(branch, case=False, na=False)]

def sum_unique_visits(data):
    numbers_in_parentheses = re.findall(r'\((\d+)\)', " ".join(data))
    return sum(map(int, numbers_in_parentheses))

def summarize_by_branch(df_branch):
    df_copy = df_branch.copy()
    for idx, row in df_copy.iterrows():
        if row['Unique transitions'] > row['Received by SMS provider']:
            df_copy.at[idx, 'Unique transitions'] = sum_unique_visits([row['Unique visits ?']])
    summary = df_copy[['Received by SMS provider', 'Delivered', 'Unique transitions']].sum()
    summary['Unique visits ?'] = sum_unique_visits(df_copy['Unique visits ?'])
    return summary.to_dict()  # Преобразуем в словарь

# Фильтрация для других категорий
def filter_by_sog(df):
    return df[df['Action'].str.contains("СОГЛ|СРЕДНЕЗА", case=False, na=False)]

def filter_by_auto(df):
    return df[df['Action'].str.contains("АВТООТВЕТЧИК|АССИC|ДРУГАЯ", case=False, na=False)]

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'file' not in request.files:
            return redirect(request.url)
        file = request.files['file']
        if file and allowed_file(file.filename):
            filename = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(filename)

            # Загружаем данные из CSV
            df = pd.read_csv(filename)

            # Ваши ветки
            df_first_branch = filter_by_branch(df, "ПЕРВАЯ ВЕТКА")
            df_second_branch = filter_by_branch(df, "ВТОРАЯ ВЕТКА")
            df_third_branch = filter_by_branch(df, "ТРЕТЬЯ ВЕТКА")
            df_drop_branch = filter_by_branch(df, "СБРОС")
            df_nocall_branch = filter_by_branch(df, "НЕДОЗВОН")
            df_press_branch = filter_by_branch(df, "ДОЖИМ")

            # Ваши дополнительные категории
            df_sog_branch = filter_by_sog(df)
            df_auto_branch = filter_by_auto(df)

            # Получаем результаты по каждой ветке и категории
            first_branch_summary = summarize_by_branch(df_first_branch)
            second_branch_summary = summarize_by_branch(df_second_branch)
            third_branch_summary = summarize_by_branch(df_third_branch)
            drop_branch_summary = summarize_by_branch(df_drop_branch)
            nocall_branch_summary = summarize_by_branch(df_nocall_branch)
            press_branch_summary = summarize_by_branch(df_press_branch)
            sog_branch_summary = summarize_by_branch(df_sog_branch)
            auto_branch_summary = summarize_by_branch(df_auto_branch)
            # Отображаем результаты
            return render_template('index.html', 
                                   first_branch_summary=first_branch_summary, 
                                   second_branch_summary=second_branch_summary,
                                   third_branch_summary=third_branch_summary,
                                   drop_branch_summary=drop_branch_summary,
                                   nocall_branch_summary=nocall_branch_summary,
                                   press_branch_summary=press_branch_summary,
                                   sog_branch_summary=sog_branch_summary,
                                   auto_branch_summary=auto_branch_summary)

    return render_template('index.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
    
