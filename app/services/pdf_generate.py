from jinja2 import Template
import subprocess
import os
import uuid


# -------------------------
# FEATURED BLOCK GENERATOR
# -------------------------
def generate_featured_block(projects):
    blocks = []

    for p in projects:
        title = p.get("title", "Untitled")
        live = p.get("live", "#")
        stack = p.get("stack", ["Tech"])
        bullets = p.get("bullets") or p.get("resume_bullets") or []

        # Ensure bullets are strings
        bullet_tex = "\n".join(
            f"\\resumeItem{{{str(b)}}}" for b in bullets
        )

        block = f"""
\\resumeProjectHeading
{{\\textbf{{\\href{{{live}}}{{{title}}}}} $|$ \\emph{{{' · '.join(stack)}}}}}{{}}
\\resumeItemListStart
{bullet_tex}
\\resumeItemListEnd
\\vspace{{-12pt}}
"""
        blocks.append(block)

    return "\n".join(blocks)


# -------------------------
# INSIGHT BLOCK GENERATOR
# -------------------------
def generate_insight_block(projects):
    blocks = []

    for i, p in enumerate(projects):
        title = p.get("title", "Untitled")
        live = p.get("live", "#")
        desc = p.get("description", "")

        block = f"""
\\resumeProjectHeading
{{\\textbf{{\\href{{{live}}}{{{title}}}}} $|$ {desc}}}{{}}
"""

        # add spacing ONLY between items
        if i < len(projects) - 1:
            block += "\n\\vspace{-25pt}\n"

        blocks.append(block)

    return "\n".join(blocks)


# -------------------------
# MAIN RENDER FUNCTION
# -------------------------
def render_latex(template_str, featured, insights):
    """
    Inject generated LaTeX blocks into template safely
    """

    featured_block = generate_featured_block(featured)
    insight_block = generate_insight_block(insights)

    # IMPORTANT: ensure strings only (fix your crash)
    if not isinstance(featured_block, str):
        featured_block = str(featured_block)

    if not isinstance(insight_block, str):
        insight_block = str(insight_block)

    # Safe replacement (NO lists allowed)
    rendered = template_str.replace(
        "{{FEATURED_PROJECTS}}",
        featured_block
    ).replace(
        "{{INSIGHT_PROJECTS}}",
        insight_block
    )

    return rendered


# -------------------------
# COMPILE PDF
# -------------------------
def compile_pdf(tex_path):
    """
    Compile LaTeX and clean all temporary files
    """

    output_dir = os.path.dirname(tex_path)
    base_name = os.path.splitext(tex_path)[0]

    subprocess.run([
        "pdflatex",
        "-interaction=nonstopmode",
        "-output-directory",
        output_dir,
        tex_path
    ], check=False)

    # -------------------------
    # CLEANUP AUX FILES
    # -------------------------
    extensions = [
        ".aux",
        ".log",
        ".out",
        ".toc",
        ".fls",
        ".fdb_latexmk"
    ]

    for ext in extensions:
        file_path = base_name + ext
        if os.path.exists(file_path):
            os.remove(file_path)


# -------------------------
# FULL PIPELINE WRAPPER
# -------------------------
def generate_resume_pipeline(template, featured, insights):

    rendered_tex = render_latex(
        template,
        featured,
        insights
    )

    output_dir = os.path.join(
        "app",
        "resume",
        "generated"
    )

    os.makedirs(output_dir, exist_ok=True)

    tex_path = os.path.join(
        output_dir,
        "resume.tex"
    )

    pdf_path = os.path.join(
        output_dir,
        "resume.pdf"
    )

    # overwrite tex
    with open(tex_path, "w", encoding="utf-8") as f:
        f.write(rendered_tex)

    compile_pdf(tex_path)

    # cleanup latex junk
    extensions = [
        ".aux",
        ".log",
        ".out",
        ".toc"
    ]

    base = tex_path.replace(".tex", "")

    for ext in extensions:
        file_path = base + ext

        if os.path.exists(file_path):
            os.remove(file_path)

    # optional:
    # remove tex file too
    if os.path.exists(tex_path):
        os.remove(tex_path)

    return {
        "pdf_path": pdf_path
    }