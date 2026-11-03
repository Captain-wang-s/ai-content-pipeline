#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSS转内联样式工具 v2 - 微信公众号专用
微信公众号会剥离<style>标签和class，只保留内联style属性。
此脚本将HTML中的所有CSS转换为内联样式。

核心逻辑:
1. 从<style>标签中提取所有CSS规则（class选择器 + 标签选择器）
2. body样式作为"全局继承"注入到每个块级元素
3. 为每个HTML标签合并：全局继承 + 标签样式 + class样式 + 已有内联样式
4. 移除<style>标签和class属性
"""

import re


def parse_all_css(css_text):
    """
    解析CSS文本，返回三类规则:
    - body_rules: body的样式（作为全局继承）
    - tag_rules: {tag_name: {prop: value}} 标签选择器
    - class_rules: {class_name: {prop: value}} 类选择器
    """
    body_rules = {}
    tag_rules = {}
    class_rules = {}
    
    # 移除注释
    css_text = re.sub(r'/\*.*?\*/', '', css_text, flags=re.DOTALL)
    
    # 解析规则块
    blocks = re.findall(r'([^{]+)\{([^}]*)\}', css_text)
    
    for selector, props_text in blocks:
        selector = selector.strip()
        props = {}
        for prop_match in re.finditer(r'([a-zA-Z-]+)\s*:\s*([^;]+)', props_text):
            prop_name = prop_match.group(1).strip()
            prop_value = prop_match.group(2).strip()
            props[prop_name] = prop_value
        
        if not props:
            continue
        
        # 分类选择器
        if selector == 'body':
            body_rules = props
        elif selector.startswith('.'):
            # 处理 .class 或 .class1.class2 或 .class:hover
            class_name = selector.lstrip('.').split(':')[0].split('.').pop()
            class_rules[class_name] = props
        elif re.match(r'^[a-z][a-z0-9]*$', selector):
            tag_rules[selector.lower()] = props
        elif ',' in selector:
            for sel in selector.split(','):
                sel = sel.strip()
                if sel == 'body':
                    body_rules.update(props)
                elif sel.startswith('.'):
                    class_name = sel.lstrip('.').split(':')[0].split('.').pop()
                    class_rules[class_name] = props
                elif re.match(r'^[a-z][a-z0-9]*$', sel):
                    tag_rules[sel.lower()] = props
    
    return body_rules, tag_rules, class_rules


def props_to_str(props):
    """将样式字典转为CSS字符串"""
    if not props:
        return ''
    return '; '.join(f'{k}: {v}' for k, v in props.items())


def inline_css(html_content):
    """
    将HTML中的所有CSS转换为内联样式
    
    Args:
        html_content: 原始HTML内容（包含<style>标签）
    
    Returns:
        转换后的HTML（所有样式为内联style属性）
    """
    # 提取所有<style>标签内容
    style_blocks = re.findall(r'<style[^>]*>(.*?)</style>', html_content, re.DOTALL)
    
    # 解析所有CSS规则
    body_rules = {}
    tag_rules = {}
    class_rules = {}
    
    for css_text in style_blocks:
        b, t, c = parse_all_css(css_text)
        body_rules.update(b)
        tag_rules.update(t)
        class_rules.update(c)
    
    # body中需要继承到块级元素的属性
    inheritable_props = {
        'font-family', 'font-size', 'line-height', 'color',
        'letter-spacing', 'word-wrap', 'text-align'
    }
    body_inherit = {k: v for k, v in body_rules.items() if k in inheritable_props}
    
    # 移除所有<style>标签
    result = re.sub(r'<style[^>]*>.*?</style>', '', html_content, flags=re.DOTALL)
    
    # 需要处理的块级标签（body样式继承到这些标签）
    block_tags = {'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'div', 'blockquote',
                  'table', 'thead', 'tbody', 'tr', 'th', 'td', 'ul', 'ol', 'li',
                  'section', 'article', 'main', 'header', 'footer', 'body'}
    
    def process_tag(match):
        full_match = match.group(0)
        tag_name = match.group(1).lower()
        attrs_str = match.group(2) or ''
        is_self_closing = match.group(3) == '/'
        
        # 解析已有的class属性
        class_attr = re.search(r'class\s*=\s*"([^"]*)"', attrs_str)
        classes = class_attr.group(1).split() if class_attr else []
        
        # 解析已有的内联style
        style_attr = re.search(r'style\s*=\s*"([^"]*)"', attrs_str)
        existing_props = {}
        if style_attr:
            for item in style_attr.group(1).split(';'):
                item = item.strip()
                if ':' in item:
                    k, v = item.split(':', 1)
                    existing_props[k.strip()] = v.strip()
        
        # 构建最终样式：body继承 + 标签样式 + class样式 + 已有内联
        final_props = {}
        
        # 1. body继承（只对块级元素）
        if tag_name in block_tags:
            final_props.update(body_inherit)
        
        # 2. 标签样式
        if tag_name in tag_rules:
            final_props.update(tag_rules[tag_name])
        
        # 3. class样式
        for cls in classes:
            if cls in class_rules:
                final_props.update(class_rules[cls])
        
        # 4. 已有内联样式（最高优先级）
        final_props.update(existing_props)
        
        if not final_props:
            # 没有样式需要设置，但仍然移除class属性
            if class_attr:
                new_attrs = re.sub(r'\s*class\s*=\s*"[^"]*"', '', attrs_str)
                if is_self_closing:
                    return f'<{match.group(1)}{new_attrs} />'
                return f'<{match.group(1)}{new_attrs}>'
            return full_match
        
        # 构建新的属性字符串
        new_attrs = attrs_str
        
        # 移除class属性
        if class_attr:
            new_attrs = re.sub(r'\s*class\s*=\s*"[^"]*"', '', new_attrs)
        
        # 移除已有的style属性
        if style_attr:
            new_attrs = re.sub(r'\s*style\s*=\s*"[^"]*"', '', new_attrs)
        
        # 添加新的内联style
        style_str = props_to_str(final_props)
        new_attrs = new_attrs.strip()
        if new_attrs:
            new_attrs = ' ' + new_attrs + ' '
        else:
            new_attrs = ' '
        new_attrs += f'style="{style_str}"'
        
        if is_self_closing:
            return f'<{match.group(1)}{new_attrs} />'
        return f'<{match.group(1)}{new_attrs}>'
    
    # 处理所有HTML标签（包括self-closing <img ... />)
    result = re.sub(
        r'<([a-zA-Z][a-zA-Z0-9]*)((?:\s[^>/]*)?)(/?)>',
        process_tag,
        result
    )
    
    return result


if __name__ == '__main__':
    test_html = '''<style>
body { font-family: -apple-system, sans-serif; font-size: 16px; line-height: 1.75; color: #1a1a1a; }
h1 { font-size: 22px; font-weight: 700; text-align: center; color: #000; }
h2 { font-size: 18px; font-weight: 700; color: #000; margin: 30px 0 15px 0; }
p { margin: 0 0 18px 0; text-align: justify; }
strong { font-weight: 700; color: #000; }
blockquote { border-left: 4px solid #ddd; padding-left: 16px; margin: 20px 0; color: #666; font-size: 15px; }
.red { color: #E53935; font-weight: 600; }
.green { color: #2E7D32; font-weight: 600; }
.notice { background-color: #FFF9E6; border-left: 4px solid #FFB800; padding: 12px 16px; }
th { background-color: #f5f5f5; font-weight: 600; padding: 10px 8px; border-bottom: 2px solid #e0e0e0; }
td { padding: 10px 8px; border-bottom: 1px solid #f0f0f0; }
hr { border: none; border-top: 1px solid #e0e0e0; margin: 25px 0; }
table { width: 100%; border-collapse: collapse; margin: 20px 0; }
</style>
<h1>测试标题</h1>
<p>普通段落</p>
<p>含<strong>加粗</strong>的段落</p>
<blockquote>引用内容</blockquote>
<p class="red">红色</p>
<div class="notice">提示框</div>
<table><tr><th>表头</th></tr><tr><td class="red">红色单元格</td></tr></table>
<hr>
<p style="text-align: center; color: #999;">已有内联样式</p>
'''
    
    result = inline_css(test_html)
    print(result)
