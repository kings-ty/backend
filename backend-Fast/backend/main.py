# main.py
from typing import Optional 
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import language_tool_python
import requests
import os
import psycopg2 
import json     
import difflib  
import datetime 
from notion_oauth import router as notion_router   

# from dotenv import load_dotenv
# load_dotenv()

app = FastAPI()
app.include_router(notion_router)
# CORS settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class WordRequest(BaseModel):
    word: str

class SaveRequest(BaseModel):
    word: str
    definition: list[str]
    synonyms: Optional[list[str]] = []

class Phonetic(BaseModel):
    text: Optional[str] = None
    audio: Optional[str] = None

class DefinitionResponse(BaseModel):
    definition: list[str]
    synonyms: list[str]
    examples: list[str]
    phonetics: list[Phonetic]

class SentenceRequest(BaseModel):
    sentence: str
    forceLLM: Optional[bool] = False

class CorrectionResponse(BaseModel):
    correctedText: str

# LanguageTool intialize
tool = language_tool_python.LanguageTool('en-GB') 


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

DB_HOST = os.getenv("DB_HOST", "127.0.0.1") 
DB_PORT = os.getenv("DB_PORT", "5432")                     
DB_NAME = os.getenv("DB_NAME", "postgres")                 
DB_USER = os.getenv("DB_USER", "postgres")                 
DB_PASSWORD = os.getenv("DB_PASSWORD", "") 


#define a function to get a database connection
def get_db_connection():
    """PostgreSQL 데이터베이스 연결을 반환합니다."""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )


class CorrectionResponse(BaseModel):
    correctedText: str

# --- Using LLm refine ---
async def refine_with_llm(text: str) -> str:
    """
    Gemini API를 호출하여 주어진 문장의 문법을 개선하고 자연스럽게 다듬습니다.
    """
    prompt = (
        "You are an expert English grammar and style corrector."
        "Your task is to correct and refine the given sentence while strictly maintaining its original meaning and nuance."
        "Ensure the output is grammatically perfect, natural, and concise."
        "If the original sentence is already perfect, return it as is. \n\n"
        f"Original: \"{text}\"\n\n"
    )

    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "temperature": 0.7, # creativity setting (0.0 ~ 1.0)
            "maxOutputTokens": 200 # maximum output tokens
        }
    }

    try:
        print(f"Calling LLM API with payload: {payload}")
        response = requests.post(api_url, json=payload)
        response.raise_for_status() # HTTP error handling

        result = response.json()
        
        if result.get("candidates") and result["candidates"][0].get("content") and result["candidates"][0]["content"].get("parts"):
            refined_text = result["candidates"][0]["content"]["parts"][0]["text"]
            return refined_text
        else:
            print(f"LLM response does not contained valid content: {result}")
            return text # LLM no valid content, return original text

    except requests.exceptions.RequestException as e:
        print(f"LLM API call error: {e}")
        return text # error occurred, return original text
    except Exception as e:
        print(f"Unknown error during LLM response processing: {e}")
        return text # error occurred, return original text

# --- 분석 데이터 JSON 객체 생성 함수 ---
def generate_analysis_data(original: str, lt_corrected: str, llm_refined: str) -> dict:
    """
    원본, LanguageTool 교정, LLM 정교화 문장을 기반으로 analysis_data JSON 객체를 생성합니다.
    """
    analysis_data = {
        "original_sentence": original,
        "language_tool_corrected": lt_corrected,
        "llm_refined_sentence": llm_refined,
        "diff_details": [],
        "type_of_miss": None, # LanguageTool missed or LLM refined
        "lt_raw_matches": [], # LanguageTool raw matches (if needed)
        "llm_notes": "No specific notes from LLM." # LLM 응답에서 추출 가능 (선택 사항)
    }

    # LanguageTool defined type of miss
    if original != lt_corrected:
        analysis_data["type_of_miss"] = "LT_CORRECTED"
    else:
     
        if original != llm_refined:
            analysis_data["type_of_miss"] = "LT_MISSED_AND_LLM_REFINED"

    # anayze differences between original and llm_refined
    s_original = original.split()
    s_llm_refined = llm_refined.split()
    
    matcher = difflib.SequenceMatcher(None, s_original, s_llm_refined)
    
    diff_details = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        original_segment = " ".join(s_original[i1:i2])
        refined_segment = " ".join(s_llm_refined[j1:j2])
        
        if tag == 'replace':
            diff_details.append({
                "type": "replace",
                "original_segment": original_segment,
                "corrected_segment": refined_segment,
                "description": f"'{original_segment}' changed to '{refined_segment}'",
                "original_start_idx": i1, 
                "original_end_idx": i2,
                "refined_start_idx": j1,
                "refined_end_idx": j2
            })
        elif tag == 'delete':
            diff_details.append({
                "type": "delete",
                "original_segment": original_segment,
                "corrected_segment": "",
                "description": f"'{original_segment}' deleted",
                "original_start_idx": i1,
                "original_end_idx": i2
            })
        elif tag == 'insert':
            diff_details.append({
                "type": "insert",
                "original_segment": "",
                "corrected_segment": refined_segment,
                "description": f"'{refined_segment}' inserted",
                "refined_start_idx": j1,
                "refined_end_idx": j2
            })
            
    analysis_data["diff_details"] = diff_details
    print(analysis_data["diff_details"])
    return analysis_data

def prioritize_definitions(meanings: list[dict]) -> list[str]:
    """Sort the array of meanings by part of speech priority and return the top 4 definitions."""
    priority = {'noun': 1, 'verb': 2, 'adjective': 3, 'adverb': 4}
    sorted_meanings = sorted(meanings, key=lambda m: priority.get(m.get('partOfSpeech'), 99))
    
    definitions = []
    for meaning in sorted_meanings:
        for definition_item in meaning.get('definitions', []):
            if len(definitions) >= 4: break
            if 'definition' in definition_item:
                definitions.append(definition_item['definition'])
        if len(definitions) >= 4: break
            
    return definitions

@app.post("/api/define", response_model=DefinitionResponse)
async def define_word(request: WordRequest):
    """Brings the definition, synonyms, examples, and phonetics of a word."""
    try:
        api_url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{request.word}"
        response = requests.get(api_url)

        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="단어를 찾을 수 없습니다.")
        response.raise_for_status()
        
        entry = response.json()[0]
        meanings = entry.get('meanings', [])
        print("Example",[d.get('example') for m in meanings for d in m.get('definitions', []) if d.get('example')][:3])
        return {
            "definition": prioritize_definitions(meanings),
            "synonyms": list(set(s for m in meanings for s in m.get('synonyms', []))),
            "examples": [d.get('example') for m in meanings for d in m.get('definitions', []) if d.get('example')][:3],
            "phonetics": [p for p in entry.get("phonetics", []) if p.get("text") or p.get("audio")]
        }

    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"외부 사전 API 호출 실패: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"서버 내부 오류: {e}")

# --- main API endpoint ---
@app.post("/api/correctSentence", response_model=CorrectionResponse)
async def correct_sentence(req: SentenceRequest):
    original_sentence = req.sentence
    force_llm_refinement = req.forceLLM
    print(f"Received sentence for correction (Original): {original_sentence}")

    # 1단계: LanguageTool을 이용한 기본 문법 및 철자 교정
    matches = tool.check(original_sentence)
    language_tool_corrected = language_tool_python.utils.correct(original_sentence, matches)
    print(f"LanguageTool matches found: {matches}")
    print(f"Sentence after LanguageTool correction: {language_tool_corrected}")

    # 2단계: LLM을 이용한 문장 정교화
    if force_llm_refinement: # Only run LLM if forceLLM is True
        text_to_refine = language_tool_corrected if language_tool_corrected else original_sentence
        refined_sentence = await refine_with_llm(text_to_refine)
        final_corrected_sentence = refined_sentence
        print(f"Sentence after LLM refinement: {refined_sentence}")
    else:
        return {"correctedText": language_tool_corrected}


    # --- Database logic start ---
    conn = None # 연결 객체를 초기화합니다.
    try:
        # 1. analysis_data JSON generate
        analysis_data = generate_analysis_data(
            original_sentence,
            language_tool_corrected,
            final_corrected_sentence
        )
        
        # 2. DB connection
        conn = get_db_connection()
        cur = conn.cursor()

        # 3. save analysis_data to auto_error_patterns table
        # original_sentence와 llm_refined_sentence are used to check if the pattern already exists
        cur.execute("""
            SELECT id, occurrence_count
            FROM auto_error_patterns
            WHERE (analysis_data->>'original_sentence') = %s
              AND (analysis_data->>'llm_refined_sentence') = %s;
        """, (original_sentence, final_corrected_sentence))
        
        existing_pattern = cur.fetchone()

        if existing_pattern:
            # if the pattern already exists, update the occurrence count
            pattern_id, current_count = existing_pattern
            new_count = current_count + 1
            cur.execute("""
                UPDATE auto_error_patterns
                SET occurrence_count = %s, detected_at = %s
                WHERE id = %s;
            """, (new_count, datetime.datetime.now(datetime.timezone.utc), pattern_id))
            print(f"Existing pattern updated (ID: {pattern_id}, New count: {new_count})")
        else:
            # new pattern, insert it
            cur.execute("""
                INSERT INTO auto_error_patterns (analysis_data, detected_at, occurrence_count)
                VALUES (%s, %s, %s);
            """, (json.dumps(analysis_data), datetime.datetime.now(datetime.timezone.utc), 1))
            print("New pattern inserted")

        conn.commit() # execute the transaction

    except psycopg2.Error as e:
        print(f"Database operation error: {e}")
        if conn:
            conn.rollback() # rollback the transaction on error
    except Exception as e:
        print(f"An unexpected error occurred during database operation: {e}")
    finally:
        if conn:
            conn.close() # close the connection to the database


    return {"correctedText": final_corrected_sentence}

