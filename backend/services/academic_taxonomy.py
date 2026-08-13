"""The single, versioned University of Rwanda academic taxonomy.

This deliberately keeps unverified programme groups empty.  Callers can offer
the explicit ``other`` selection instead of presenting a guessed programme.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional


@dataclass(frozen=True)
class AcademicNode:
    id: str
    name: str
    slug: str
    parent_id: Optional[str] = None
    active: bool = True
    order: int = 0
    description: Optional[str] = None


INSTITUTION = AcademicNode("ur", "University of Rwanda", "university-of-rwanda", order=1)
_tree = {
 "huye": ("Huye Campus", {"cass": ("College of Arts and Social Sciences (CASS)", {"arts": ("School of Arts, Languages and Communication Studies", []), "social": ("School of Social Studies and Governance", [])}), "cbe": ("College of Business and Economics (CBE)", {"business": ("School of Business", []), "economics": ("School of Economics", [])}), "cmhs": ("College of Medicine and Health Sciences (CMHS)", {"health": ("Health and medical studies", [])})}),
 "gikondo": ("Gikondo Campus", {"cass": ("College of Arts and Social Sciences (CASS)", {"social": ("School of Social Studies and Governance", [])}), "cbe": ("College of Business and Economics (CBE)", {"business": ("School of Business", []), "economics": ("School of Economics", []), "ace-data": ("African Centre of Excellence in Data Science", [])}), "caff": ("College of Agriculture, Forestry and Food Science (CAFF)", {"agriculture": ("School of Agriculture and Food Sciences", [])})}),
 "remera": ("Remera Campus", {"cmhs": ("College of Medicine and Health Sciences (CMHS)", {"medicine": ("School of Medicine and Pharmacy", ["MBBS", "BSc Pharmacy", "BSc Clinical Psychology", "MSc Clinical Anatomy", "MSc Medical Physiology", "MSc Human Genetics and Genomics", "MSc Clinical Trials", "MSc Clinical Psychology and Therapeutics", "MSc Immunology", "Master of Medicine specializations"]), "public-health": ("School of Public Health", ["BSc Environmental Health Sciences", "BSc Human Nutrition and Dietetics", "Master of Public Health", "MSc Epidemiology", "Master in Field Epidemiology"])})}),
 "nyarugenge": ("Nyarugenge Campus", {"cst": ("College of Science and Technology (CST)", {"built": ("School of Architecture and Built Environment", ["BSc Quantity Surveying", "BSc Estate Management & Valuation", "BSc Urban & Regional Planning", "Bachelor of Design in Visual Design", "Bachelor of Design in Industrial Design", "Bachelor of Creative Design", "BSc Geography: Urban Planning"]), "engineering": ("School of Engineering", ["Civil Engineering", "Environmental Engineering", "Geotechnical Engineering", "Water Resources & Environmental Engineering", "Surveying & Geomatics Engineering", "Mechanical Engineering", "Production Engineering", "Plant Engineering", "Energy Engineering", "Electronics & Telecommunications Engineering"]), "ict": ("School of ICT", []), "mining": ("School of Mining and Geology", ["BSc Mining Engineering", "BSc Applied Geology"]), "science": ("School of Science", ["BSc Statistics", "BSc Biotechnology", "BSc Applied Physics", "BSc Analytical Chemistry", "BSc Applied Geology"])})}),
 "busogo": ("Busogo Campus", {"caff": ("College of Agriculture, Forestry and Food Science (CAFF)", {"agriculture": ("School of Agriculture and Food Sciences", ["Food Safety and Quality", "Agroforestry and Soil Management", "Crop Sciences", "Circular Agro-Economy"]), "ag-engineering": ("School of Agricultural Engineering", ["Agricultural Land & Irrigation Engineering"]), "forestry": ("School of Forestry, Ecotourism, and Greenspace Management", ["Ecotourism & Greenspace Management"])})}),
 "rukara": ("Rukara Campus", {"education": ("College of Education (CE)", {"math-science": ("School of Mathematics and Science Education", ["BEd Mathematics–Geography", "BEd Mathematics–Computer Science", "BEd Mathematics–Economics", "BEd Mathematics–Biology", "BEd Mathematics–Chemistry", "BEd Physical Education and Sports", "BEd Biology & Physical Education and Sports", "BEd Computer Science", "MEd Biology", "PhD Biology Education", "PhD Chemistry Education", "PhD Physics Education", "PhD Science Education"])})}),
 "nyagatare": ("Nyagatare Campus", {"cvas": ("College of Veterinary Medicine and Animal Sciences (CVAS)", {"animal": ("School of Animal Sciences and Biotechnology", ["Animal Production", "Animal Sciences", "Animal Biotechnology", "MSc Animal Production"])})}),
 "rwamagana": ("Rwamagana Campus", {}),
}

def _slug(value: str) -> str:
    return "".join(c.lower() if c.isalnum() else "-" for c in value).strip("-").replace("--", "-")

NODES: dict[str, AcademicNode] = {INSTITUTION.id: INSTITUTION}
for ci, (campus_key, (campus_name, colleges)) in enumerate(_tree.items(), 1):
    campus_id = f"ur-campus-{campus_key}"; NODES[campus_id] = AcademicNode(campus_id, campus_name, campus_key, "ur", order=ci)
    for coi, (college_key, (college_name, schools)) in enumerate(colleges.items(), 1):
        college_id = f"{campus_id}-college-{college_key}"; NODES[college_id] = AcademicNode(college_id, college_name, college_key, campus_id, order=coi)
        for si, (school_key, (school_name, programmes)) in enumerate(schools.items(), 1):
            school_id = f"{college_id}-school-{school_key}"; NODES[school_id] = AcademicNode(school_id, school_name, school_key, college_id, order=si, description="Programmes are still being verified." if not programmes else None)
            for pi, programme in enumerate(programmes, 1):
                programme_id = f"{school_id}-programme-{_slug(programme)}"; NODES[programme_id] = AcademicNode(programme_id, programme, _slug(programme), school_id, order=pi)

def children(parent_id: str) -> list[dict]:
    return [asdict(node) for node in sorted(NODES.values(), key=lambda x: x.order) if node.parent_id == parent_id and node.active]

def tree() -> dict:
    return {"institution": asdict(INSTITUTION), "nodes": [asdict(node) for node in NODES.values()]}

def validate_context(institution_id: Optional[str], campus_id: Optional[str], college_id: Optional[str], school_id: Optional[str], programme_id: Optional[str], academic_department_id: Optional[str] = None) -> None:
    if academic_department_id is not None:
        # The supplied UR structure does not verify any departments yet.
        raise ValueError("Academic departments are not currently available in the taxonomy")
    values = [institution_id, campus_id, college_id, school_id, programme_id]
    if not any(values): return
    if institution_id != "ur": raise ValueError("Unknown institution")
    parent = "ur"
    for node_id in values[1:]:
        if node_id is None: continue
        if node_id == "other" and parent != "ur":
            continue
        node = NODES.get(node_id)
        if not node or node.parent_id != parent: raise ValueError("Academic selections do not form a valid University of Rwanda hierarchy")
        parent = node_id

def context_names(campus_id: Optional[str], college_id: Optional[str], school_id: Optional[str], programme_id: Optional[str]) -> dict[str, Optional[str]]:
    return {"college_name": NODES[college_id].name if college_id in NODES else None,
            "department_name": NODES[programme_id].name if programme_id in NODES else (NODES[school_id].name if school_id in NODES else None)}
