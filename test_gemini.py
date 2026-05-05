import google.generativeai as genai
genai.configure(api_key='AIzaSyDSyHQ1oQOe3dSsd3fx2eWEzmJ1L4AFv9M')

for m in genai.list_models():
    if 'embedContent' in m.supported_generation_methods:
        print(m.name)
