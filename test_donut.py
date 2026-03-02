from transformers import DonutProcessor, VisionEncoderDecoderModel
from PIL import Image
import torch

model_name = "naver-clova-ix/donut-base-finetuned-docvqa"

processor = DonutProcessor.from_pretrained(model_name)
model = VisionEncoderDecoderModel.from_pretrained(
    model_name,
    use_safetensors=True
)

device = "cuda" if torch.cuda.is_available() else "cpu"
model.to(device)

image = Image.open("sample_invoice.png").convert("RGB")
pixel_values = processor(image, return_tensors="pt").pixel_values.to(device)

task_prompt = "<s_docvqa><s_question>What is the total amount?</s_question><s_answer>"
decoder_input_ids = processor.tokenizer(
    task_prompt,
    add_special_tokens=False,
    return_tensors="pt"
).input_ids.to(device)

outputs = model.generate(
    pixel_values,
    decoder_input_ids=decoder_input_ids,
    max_length=512
)

result = processor.batch_decode(outputs, skip_special_tokens=True)[0]
print("RESULT:\n", result)