"""
Seed script — populates 60+ real-world certifications across categories.
Run from the backend directory:
    python scripts/seed_certifications.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.models.certification import Certification

CERTIFICATIONS = [
    # ── Cloud Computing — AWS ──────────────────────────────────────────────
    dict(title="AWS Certified Solutions Architect – Associate", provider="Amazon Web Services", category="Cloud Computing", level="Associate", duration="3 months", tags="aws,cloud,architecture,associate", description="Design and deploy scalable, highly available systems on AWS.", prerequisites="Cloud Fundamentals\n2+ years experience"),
    dict(title="AWS Certified Solutions Architect – Professional", provider="Amazon Web Services", category="Cloud Computing", level="Professional", duration="4 months", tags="aws,cloud,architecture,professional", description="Advanced AWS architecture for complex distributed systems.", prerequisites="Solutions Architect Associate\n5+ years experience"),
    dict(title="AWS Certified Developer – Associate", provider="Amazon Web Services", category="Cloud Computing", level="Associate", duration="2 months", tags="aws,cloud,developer,associate", description="Develop and maintain AWS-based applications.", prerequisites="Programming experience\nAWS basics"),
    dict(title="AWS Certified SysOps Administrator – Associate", provider="Amazon Web Services", category="Cloud Computing", level="Associate", duration="2.5 months", tags="aws,cloud,sysops,operations", description="Deploy, manage, and operate scalable systems on AWS.", prerequisites="Linux basics\nAWS fundamentals"),
    dict(title="AWS Certified DevOps Engineer – Professional", provider="Amazon Web Services", category="Cloud Computing", level="Professional", duration="4 months", tags="aws,devops,cloud,professional,cicd", description="Implement and manage continuous delivery pipelines on AWS.", prerequisites="Developer or SysOps Associate"),
    dict(title="AWS Certified Cloud Practitioner", provider="Amazon Web Services", category="Cloud Computing", level="Foundational", duration="1 month", tags="aws,cloud,foundational,beginner", description="Foundational understanding of AWS Cloud concepts and services.", prerequisites="None"),
    dict(title="AWS Certified Security – Specialty", provider="Amazon Web Services", category="Cloud Computing", level="Specialty", duration="3 months", tags="aws,cloud,security,specialty", description="Securing AWS workloads, IAM, encryption, and compliance.", prerequisites="2+ years AWS security experience"),
    dict(title="AWS Certified Data Analytics – Specialty", provider="Amazon Web Services", category="Cloud Computing", level="Specialty", duration="3 months", tags="aws,cloud,data,analytics,specialty", description="Designing and implementing AWS analytics solutions.", prerequisites="5 years data analytics experience"),
    dict(title="AWS Certified Machine Learning – Specialty", provider="Amazon Web Services", category="Cloud Computing", level="Specialty", duration="3 months", tags="aws,cloud,ml,machine learning,specialty", description="Building, training, and deploying ML models on AWS.", prerequisites="2+ years ML experience"),

    # ── Cloud Computing — Microsoft Azure ─────────────────────────────────
    dict(title="Microsoft Azure Fundamentals (AZ-900)", provider="Microsoft", category="Cloud Computing", level="Foundational", duration="1 month", tags="azure,cloud,microsoft,foundational,az-900", description="Core cloud concepts and foundational Azure services.", prerequisites="None"),
    dict(title="Microsoft Azure Administrator (AZ-104)", provider="Microsoft", category="Cloud Computing", level="Associate", duration="2.5 months", tags="azure,cloud,administrator,az-104", description="Implement, manage, and monitor Azure environments.", prerequisites="Azure Basics"),
    dict(title="Microsoft Azure Developer Associate (AZ-204)", provider="Microsoft", category="Cloud Computing", level="Associate", duration="2.5 months", tags="azure,cloud,developer,az-204", description="Develop and maintain cloud applications using Azure services.", prerequisites="Azure Basics\nProgramming knowledge"),
    dict(title="Microsoft Azure Solutions Architect Expert (AZ-305)", provider="Microsoft", category="Cloud Computing", level="Expert", duration="4 months", tags="azure,cloud,architect,az-305", description="Design Azure solutions including compute, networking, storage and security.", prerequisites="AZ-104 or equivalent"),
    dict(title="Microsoft Azure DevOps Engineer Expert (AZ-400)", provider="Microsoft", category="Cloud Computing", level="Expert", duration="3.5 months", tags="azure,devops,cloud,az-400,cicd", description="Design and implement DevOps practices in Azure.", prerequisites="AZ-104 or AZ-204"),
    dict(title="Microsoft Azure AI Fundamentals (AI-900)", provider="Microsoft", category="Cloud Computing", level="Foundational", duration="1 month", tags="azure,ai,microsoft,foundational,ai-900", description="Core AI and machine learning concepts on Azure.", prerequisites="None"),
    dict(title="Microsoft Azure Data Fundamentals (DP-900)", provider="Microsoft", category="Cloud Computing", level="Foundational", duration="1 month", tags="azure,data,microsoft,foundational,dp-900", description="Foundational knowledge of data concepts and Azure data services.", prerequisites="None"),
    dict(title="Microsoft Azure Security Technologies (AZ-500)", provider="Microsoft", category="Cloud Computing", level="Associate", duration="3 months", tags="azure,security,cloud,az-500", description="Implement security controls and protect Azure resources.", prerequisites="AZ-104 recommended"),

    # ── Cloud Computing — Google Cloud ────────────────────────────────────
    dict(title="Google Cloud Digital Leader", provider="Google Cloud", category="Cloud Computing", level="Foundational", duration="1 month", tags="gcp,google,cloud,foundational", description="Overview of Google Cloud products and their business value.", prerequisites="None"),
    dict(title="Google Cloud Associate Cloud Engineer", provider="Google Cloud", category="Cloud Computing", level="Associate", duration="2.5 months", tags="gcp,google,cloud,engineer,associate", description="Deploy and manage Google Cloud applications and infrastructure.", prerequisites="6 months GCP experience"),
    dict(title="Google Cloud Professional Cloud Architect", provider="Google Cloud", category="Cloud Computing", level="Professional", duration="4 months", tags="gcp,google,cloud,architect,professional", description="Design, develop, and manage scalable GCP solutions.", prerequisites="3+ years industry experience"),
    dict(title="Google Cloud Professional Data Engineer", provider="Google Cloud", category="Cloud Computing", level="Professional", duration="3.5 months", tags="gcp,google,cloud,data,professional", description="Design and build data processing systems on GCP.", prerequisites="3+ years data engineering experience"),
    dict(title="Google Cloud Professional DevOps Engineer", provider="Google Cloud", category="Cloud Computing", level="Professional", duration="3 months", tags="gcp,google,cloud,devops,professional,sre", description="Build software delivery pipelines and manage Google Cloud infrastructure.", prerequisites="3+ years DevOps experience"),

    # ── Programming — Java ────────────────────────────────────────────────
    dict(title="Oracle Certified Foundations Associate – Java", provider="Oracle", category="Programming", level="Foundational", duration="1.5 months", tags="java,oracle,programming,foundational,ocp", description="Basic understanding of Java programming fundamentals.", prerequisites="None"),
    dict(title="Oracle Certified Professional Java SE 17 Developer", provider="Oracle", category="Programming", level="Professional", duration="3 months", tags="java,oracle,programming,se17,ocp", description="Advanced Java SE 17 development concepts including streams, lambdas, modules.", prerequisites="Java programming basics"),
    dict(title="Oracle Certified Professional – Java EE 7 Application Developer", provider="Oracle", category="Programming", level="Professional", duration="4 months", tags="java,javaee,enterprise,oracle,programming", description="Build enterprise Java applications using Java EE 7 technologies.", prerequisites="Java SE proficiency"),
    dict(title="Spring Professional Certification", provider="VMware/Pivotal", category="Programming", level="Professional", duration="2 months", tags="java,spring,springboot,programming,vmware", description="Core Spring Framework and Spring Boot development.", prerequisites="Java experience"),

    # ── Programming — Python ──────────────────────────────────────────────
    dict(title="PCEP – Certified Entry-Level Python Programmer", provider="Python Institute", category="Programming", level="Entry", duration="1 month", tags="python,programming,pcep,beginner", description="Entry-level Python programming including syntax, data types, and control flow.", prerequisites="None"),
    dict(title="PCAP – Certified Associate Python Programmer", provider="Python Institute", category="Programming", level="Associate", duration="2 months", tags="python,programming,pcap,oop", description="Python fundamentals including OOP, exceptions, and modules.", prerequisites="PCEP or equivalent"),
    dict(title="PCPP1 – Certified Professional Python Programmer 1", provider="Python Institute", category="Programming", level="Professional", duration="3 months", tags="python,programming,pcpp,advanced", description="Advanced Python including generators, decorators, files, and networks.", prerequisites="PCAP"),
    dict(title="TensorFlow Developer Certificate", provider="Google", category="Programming", level="Associate", duration="2 months", tags="python,tensorflow,ml,ai,google,programming", description="Build and train neural networks using TensorFlow and Keras.", prerequisites="Python\nBasic ML knowledge"),

    # ── Programming — C / C++ / C# / .NET ────────────────────────────────
    dict(title="CLA – C Programming Language Certified Associate", provider="C++ Institute", category="Programming", level="Associate", duration="1.5 months", tags="c,programming,cla,clanguage", description="Core C programming language syntax, data types, control structures.", prerequisites="None"),
    dict(title="CPA – C++ Certified Associate Programmer", provider="C++ Institute", category="Programming", level="Associate", duration="2 months", tags="cpp,c++,programming,cpa", description="C++ programming fundamentals including OOP concepts.", prerequisites="Basic programming knowledge"),
    dict(title="CPP – C++ Certified Professional Programmer", provider="C++ Institute", category="Programming", level="Professional", duration="3 months", tags="cpp,c++,programming,cpp,advanced", description="Advanced C++ including templates, STL, memory management.", prerequisites="CPA or equivalent"),
    dict(title="Microsoft Certified: Azure Developer Associate (C#/.NET)", provider="Microsoft", category="Programming", level="Associate", duration="2.5 months", tags="csharp,dotnet,.net,microsoft,programming,az-204", description="Build cloud applications with C# and the .NET ecosystem on Azure.", prerequisites="C# basics\nAzure familiarity"),
    dict(title=".NET MAUI Certified Developer", provider="Microsoft", category="Programming", level="Associate", duration="2 months", tags="dotnet,.net,maui,mobile,cross-platform,csharp", description="Build cross-platform mobile and desktop apps with .NET MAUI.", prerequisites=".NET / C# experience"),

    # ── ServiceNow ────────────────────────────────────────────────────────
    dict(title="ServiceNow Certified System Administrator (CSA)", provider="ServiceNow", category="ServiceNow", level="Foundational", duration="1.5 months", tags="servicenow,csa,itsm,admin", description="Administer and configure the ServiceNow platform.", prerequisites="Basic IT knowledge"),
    dict(title="ServiceNow Certified Application Developer (CAD)", provider="ServiceNow", category="ServiceNow", level="Associate", duration="2 months", tags="servicenow,cad,developer,scripting", description="Build custom applications on the ServiceNow platform using scripting.", prerequisites="CSA"),
    dict(title="ServiceNow Certified Implementation Specialist – ITSM (CIS-ITSM)", provider="ServiceNow", category="ServiceNow", level="Specialist", duration="2.5 months", tags="servicenow,itsm,cis,implementation", description="Implement and configure the ITSM application suite in ServiceNow.", prerequisites="CSA + ITSM experience"),
    dict(title="ServiceNow Certified Implementation Specialist – HRSD", provider="ServiceNow", category="ServiceNow", level="Specialist", duration="2 months", tags="servicenow,hrsd,hr,cis", description="Implement HR Service Delivery on the ServiceNow platform.", prerequisites="CSA + HR knowledge"),
    dict(title="ServiceNow Certified Implementation Specialist – SecOps", provider="ServiceNow", category="ServiceNow", level="Specialist", duration="2.5 months", tags="servicenow,secops,security,cis", description="Implement Security Operations module in ServiceNow.", prerequisites="CSA + security knowledge"),
    dict(title="ServiceNow Certified Master Architect (CMA)", provider="ServiceNow", category="ServiceNow", level="Expert", duration="6 months", tags="servicenow,cma,architect,expert", description="Expert-level ServiceNow platform architecture and governance.", prerequisites="Multiple CIS certifications"),

    # ── DevOps / Cloud Infrastructure ─────────────────────────────────────
    dict(title="CKA – Certified Kubernetes Administrator", provider="CNCF / Linux Foundation", category="DevOps", level="Professional", duration="3 months", tags="kubernetes,cka,devops,containers,k8s", description="Configure, deploy and manage Kubernetes clusters.", prerequisites="Linux basics\nDocker basics"),
    dict(title="CKAD – Certified Kubernetes Application Developer", provider="CNCF / Linux Foundation", category="DevOps", level="Professional", duration="2.5 months", tags="kubernetes,ckad,devops,containers,developer", description="Design, build, and deploy cloud-native applications on Kubernetes.", prerequisites="Docker\nBasic Kubernetes"),
    dict(title="HashiCorp Certified: Terraform Associate", provider="HashiCorp", category="DevOps", level="Associate", duration="1.5 months", tags="terraform,iac,devops,infrastructure,hashicorp", description="Infrastructure-as-Code using Terraform for cloud provisioning.", prerequisites="Basic cloud knowledge"),
    dict(title="Docker Certified Associate (DCA)", provider="Docker", category="DevOps", level="Associate", duration="2 months", tags="docker,containers,dca,devops", description="Container lifecycle management, security, orchestration with Docker.", prerequisites="Linux basics"),
    dict(title="Red Hat Certified Engineer (RHCE)", provider="Red Hat", category="DevOps", level="Professional", duration="3 months", tags="redhat,linux,rhce,devops,automation,ansible", description="Automate Red Hat Enterprise Linux tasks using Ansible.", prerequisites="RHCSA"),

    # ── Development ───────────────────────────────────────────────────────
    dict(title="Meta Front-End Developer Professional Certificate", provider="Meta / Coursera", category="Development", level="Professional", duration="7 months", tags="frontend,react,javascript,html,css,meta", description="Build responsive React apps with modern front-end techniques.", prerequisites="Basic computer skills"),
    dict(title="Meta Back-End Developer Professional Certificate", provider="Meta / Coursera", category="Development", level="Professional", duration="8 months", tags="backend,python,django,api,meta", description="Build back-end web services with Python, Django, and APIs.", prerequisites="Basic programming"),
    dict(title="Full Stack Web Developer – IBM Professional Certificate", provider="IBM / Coursera", category="Development", level="Professional", duration="6 months", tags="fullstack,node,react,mongodb,ibm", description="Build full stack applications using Node.js, React, MongoDB.", prerequisites="Basic programming"),
    dict(title="Angular Developer Certification", provider="Google / Angular", category="Development", level="Associate", duration="2 months", tags="angular,typescript,frontend,javascript,development", description="Build enterprise-grade SPAs with Angular and TypeScript.", prerequisites="JavaScript / TypeScript basics"),
    dict(title="MongoDB Associate Developer", provider="MongoDB", category="Development", level="Associate", duration="2 months", tags="mongodb,nosql,database,development,mdb", description="Build applications using MongoDB CRUD operations, aggregation, indexing.", prerequisites="Programming basics"),

    # ── Testing / QA ──────────────────────────────────────────────────────
    dict(title="ISTQB Certified Tester Foundation Level (CTFL)", provider="ISTQB", category="Testing", level="Foundation", duration="1.5 months", tags="istqb,testing,qa,quality,ctfl", description="Software testing fundamentals — test design, management, and tools.", prerequisites="None"),
    dict(title="ISTQB Advanced Test Analyst", provider="ISTQB", category="Testing", level="Advanced", duration="3 months", tags="istqb,testing,qa,advanced,test analyst", description="Advanced techniques for test analysis, design, and management.", prerequisites="CTFL"),
    dict(title="Certified Selenium Tester", provider="ASTQB / Selenium", category="Testing", level="Associate", duration="2 months", tags="selenium,automation,testing,qa,webdriver", description="Automated web testing with Selenium WebDriver.", prerequisites="Programming basics"),
    dict(title="Cypress Test Automation Engineer", provider="Cypress.io", category="Testing", level="Associate", duration="1.5 months", tags="cypress,automation,testing,javascript,qa", description="End-to-end test automation with Cypress for modern web apps.", prerequisites="JavaScript basics"),
    dict(title="Certified Agile Tester (CAT)", provider="iSQI", category="Testing", level="Associate", duration="1 month", tags="agile,testing,scrum,qa,cat", description="Testing in Agile environments — sprint testing, continuous integration.", prerequisites="Basic testing knowledge"),

    # ── IT Support / ITSM ─────────────────────────────────────────────────
    dict(title="ITIL 4 Foundation", provider="AXELOS / PeopleCert", category="Support", level="Foundation", duration="1.5 months", tags="itil,itsm,support,service management,itil4", description="Foundational ITSM concepts — service value chain, practices, and key terms.", prerequisites="None"),
    dict(title="ITIL 4 Specialist – Create, Deliver and Support", provider="AXELOS / PeopleCert", category="Support", level="Specialist", duration="2 months", tags="itil,itsm,support,specialist,cds", description="Integrate different value streams and activities to deliver services.", prerequisites="ITIL 4 Foundation"),
    dict(title="CompTIA A+", provider="CompTIA", category="Support", level="Foundation", duration="3 months", tags="comptia,a+,hardware,support,it,helpdesk", description="Essential hardware, networking, and troubleshooting skills for IT support.", prerequisites="None"),
    dict(title="CompTIA Network+", provider="CompTIA", category="Support", level="Associate", duration="2.5 months", tags="comptia,network+,networking,support", description="Networking concepts, infrastructure, operations, and security.", prerequisites="CompTIA A+ recommended"),
    dict(title="CompTIA Security+", provider="CompTIA", category="Support", level="Associate", duration="2.5 months", tags="comptia,security+,security,support,cybersecurity", description="Core cybersecurity concepts, threats, vulnerabilities, and risk management.", prerequisites="Network+"),
    dict(title="HDI Customer Service Representative (HDI-CSR)", provider="HDI", category="Support", level="Foundation", duration="1 month", tags="hdi,support,customer service,helpdesk,csr", description="Customer service skills for technical support and help desk roles.", prerequisites="None"),
]


def seed():
    db = SessionLocal()
    try:
        existing = db.query(Certification).count()
        if existing > 0:
            print(f"✓ {existing} certifications already exist. Skipping seed.")
            print("  To re-seed, delete existing certifications first.")
            return

        added = 0
        for cert_data in CERTIFICATIONS:
            cert = Certification(**cert_data)
            db.add(cert)
            added += 1

        db.commit()
        print(f"[OK] Seeded {added} certifications successfully.")
    except Exception as e:
        db.rollback()
        print(f"[ERR] Error seeding certifications: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
