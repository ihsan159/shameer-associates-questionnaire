import json
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def main():
    with open('static/questionnaire_schema.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    print(f"Title: {data.get('title')}")
    print("\nChapters:")
    for ch in data.get('chapters', []):
        print(f"\n- {ch['id']} ({ch['number']}): {ch['title']}")
        print(f"  Description: {ch['description']}")
        print("  Sections:")
        for sec in ch.get('sections', []):
            print(f"    * {sec['id']} ({sec.get('number', '')}): {sec['title']} [Type: {sec.get('type', 'standard')}]")
            if 'questions' in sec:
                print(f"      Questions: {len(sec['questions'])}")
                for q in sec['questions']:
                    print(f"        - {q['id']} ({q['type']}): {q['label'][:40]}... (dependsOn: {q.get('dependsOn') is not None})")
            else:
                print("      (No questions array)")

if __name__ == '__main__':
    main()
