import re, warnings
from typing import Callable, Optional, Union, Dict
from typing_extensions import Protocol
from imas_tools.story.story_csv import StoryCsv
from imas_tools.story.gakuen_parser import parse_messages

class Merger(Protocol):
    def __call__(
        self,
        original_text: str,
        translated_text: str,
        validation_original_text: Optional[str] = None,
        *,
        is_choice: bool = False,
    ) -> str: ...


def merge_translated_csv_into_txt(
    csv_text: Union[str, list[str]],
    gakuen_txt: str,
    merger: Merger,
    name_dict: Optional[Dict[str, str]] = None,
) -> str:
    story_csv = StoryCsv(csv_text)
    parsed = parse_messages(gakuen_txt)
    iterator = iter(story_csv.data)

    # 收集所有需要进行的替换操作
    replacements = []
    
    for line in parsed:
        if line["__tag__"] == "message" or line["__tag__"] == "narration":
            if line.get("text"):
                next_csv_line = next(iterator)
                new_text = merger(
                    line["text"], next_csv_line["trans"], next_csv_line["text"]
                )
                replacements.append({
                    "old": line['text'],
                    "new": new_text,
                    "pattern": "text",
                    "length": len(line['text'])
                })
        elif line["__tag__"] == "title":
            if line.get("title"):
                next_csv_line = next(iterator)
                new_text = merger(
                    line["title"], next_csv_line["trans"], next_csv_line["text"]
                )
                replacements.append({
                    "old": line['title'],
                    "new": new_text,
                    "pattern": "title",
                    "length": len(line['title'])
                })
        elif line["__tag__"] == "choicegroup":
            if isinstance(line["choices"], list):
                for choice in line["choices"]:
                    next_csv_line = next(iterator)
                    new_text = merger(
                        choice["text"],
                        next_csv_line["trans"],
                        next_csv_line["text"],
                        is_choice=True,
                    )
                    replacements.append({
                        "old": choice['text'],
                        "new": new_text,
                        "pattern": "text",
                        "length": len(choice['text'])
                    })
            elif isinstance(line["choices"], dict):
                next_csv_line = next(iterator)
                new_text = merger(
                    line["choices"]["text"],
                    next_csv_line["trans"],
                    next_csv_line["text"],
                    is_choice=True,
                )
                replacements.append({
                    "old": line["choices"]["text"],
                    "new": new_text,
                    "pattern": "text",
                    "length": len(line["choices"]["text"])
                })
    
    # 按文本长度从长到短排序，避免短相似文本优先匹配的问题
    replacements.sort(key=lambda x: x["length"], reverse=True)
    
    # 执行替换 - 使用正则表达式进行更精确的匹配
    for replacement in replacements:
        old_text = replacement["old"]
        new_text = replacement["new"]
        pattern_name = replacement["pattern"]
        
        # 转义正则表达式特殊字符
        escaped_old = re.escape(old_text)
        
        # 匹配完整的属性，确保只替换一次
        regex_pattern = f'{pattern_name}={escaped_old}(?=[\\s\\]])'
        regex_replacement = f'{pattern_name}={new_text}'
        
        gakuen_txt = re.sub(regex_pattern, regex_replacement, gakuen_txt, count=1)
    
    # 使用人名字典替换人名
    if name_dict:
        # 按人名长度从长到短排序，避免短人名优先匹配的问题
        sorted_names = sorted(name_dict.items(), key=lambda x: len(x[0]), reverse=True)
        for jp_name, cn_name in sorted_names:
            # 使用正则表达式匹配 name=日文名，确保是完整的属性值
            escaped_name = re.escape(jp_name)
            pattern = f'name={escaped_name}(?=[\\s\\]])'
            replacement = f'name={cn_name}'
            gakuen_txt = re.sub(pattern, replacement, gakuen_txt)
    
    return gakuen_txt


def trivial_translation_merger(
    original_text: str,
    translated_text: str,
    validation_original_text: Optional[str] = None,
    *,
    is_choice=False,
):
    translated_text = escape_equals(translated_text)
    if (
        validation_original_text is not None
        and validation_original_text != original_text
    ):
        raise ValueError(
            f"Original text does not match validation text: {validation_original_text} != {original_text}"
        )
    return translated_text


# <r\=はなみさき>花海咲季</r>hihihi -> 花海咲季hihihi
def remove_r_elements(input_string):
    pattern = r"<r\\=.*?>(.*?)</r>"
    cleaned_string = re.sub(pattern, r"\1", input_string)
    return (cleaned_string.replace("―", "—").replace(r"<em\=>", "")
            .replace("</em>", "").replace("<em>", ""))

# bare "=" is not allowed
# replace all bare "=" with r"\n"
def escape_equals(text):
    return re.sub(r"(?<!\\)=", r"\\=", text)


# eg <r\=はなみさき>花海咲季</r>
def line_level_dual_lang_translation_merger(
    original_text: str,
    translated_text: str,
    validation_original_text: Optional[str] = None,
    *,
    is_choice=False,
):
    if (
        validation_original_text is not None
        and validation_original_text != original_text
    ):
        raise ValueError(
            f"Original text does not match validation text: {validation_original_text} != {original_text}"
        )
    if is_choice:
        # return f"{original_text}\\n{translated_text}"
        return translated_text
    # if line level doesn't match, fallback
    if abs(len(original_text.split("\\n")) - len(translated_text.split("\\n"))) > 1:
        warnings.warn(
            f"Line level doesn't match, fallback to trivial translation merger\nOriginal text: {original_text}\nTranslated text: {translated_text}\n"
        )
        return trivial_translation_merger(
            original_text, translated_text, validation_original_text
        )

    original_text = remove_r_elements(original_text)
    translated_text = remove_r_elements(escape_equals(translated_text))
    if len(original_text.split("\\n")) < len(translated_text.split("\\n")):
        text_len = len(original_text)
        original_text = (
            original_text[0 : text_len // 2] + "\\n" + original_text[text_len // 2 :]
        )
    if len(original_text.split("\\n")) > len(translated_text.split("\\n")):
        original_text = original_text.replace("\\n", " ")
    binds = zip(original_text.split("\\n"), translated_text.split("\\n"))
    texts = []
    for item in binds:
        if any(item):
            texts.append(f"<r\\={item[0]}>{item[1]}</r>")
    return "\\r\\n".join(texts)
