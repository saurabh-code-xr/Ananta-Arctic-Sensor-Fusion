"""
LinkedIn Article Fetcher
Reads all Eva Sula articles and saves to a single dump file
for AI analysis and strategy building.
"""

import time
import os

URLS = [
    # --- Original batch (19 articles) ---
    "https://www.linkedin.com/pulse/revolutionising-defence-autonomous-systems-how-achieve-eva-sula-o1knf/",
    "https://www.linkedin.com/pulse/digital-culture-militaries-myth-fiction-useful-tool-commanders-sula-fbrbf/",
    "https://www.linkedin.com/pulse/uncrewed-systems-just-piece-hardware-bit-more-eva-sula-tcfof/",
    "https://www.linkedin.com/pulse/nato-digital-ocean-industry-symposium-takeaways-eva-sula-kfewf/",
    "https://www.linkedin.com/pulse/digital-culture-military-commanders-challenge-opportunity-eva-sula-9crff/",
    "https://www.linkedin.com/pulse/ai-digital-innovation-defence-call-action-eva-sula-gpylf/",
    "https://www.linkedin.com/pulse/ai-defence-practical-approach-command-control-eva-sula-vqryf/",
    "https://www.linkedin.com/pulse/autonomous-systems-digital-backbone-security-resilience-eva-sula-tcu0f/",
    "https://www.linkedin.com/pulse/readiness-gap-overcoming-hurdles-modern-warfare-eva-sula-bsgcf/",
    "https://www.linkedin.com/pulse/digital-culture-defence-from-strategy-superiority-eva-sula-vhq9f/",
    "https://www.linkedin.com/pulse/autonomous-uncrewed-systems-next-frontier-command-control-eva-sula-kapyf/",
    "https://www.linkedin.com/pulse/maskirovka-oldest-russian-tactic-never-died-eva-sula-ghwdf/",
    "https://www.linkedin.com/pulse/part-2-vranyo-ritualised-lie-eva-sula-dojhf/",
    "https://www.linkedin.com/pulse/part-2-real-ai-stack-behind-autonomy-why-most-people-never-eva-sula-bbjif/",
    "https://www.linkedin.com/pulse/part-3-potemkin-logic-from-imperial-theatre-modern-russian-eva-sula-7uujf/",
    "https://www.linkedin.com/pulse/electromagnetic-warfare-blind-spot-we-cant-afford-ignore-eva-sula-j78cf/",
    "https://www.linkedin.com/pulse/part-4-fontanka-16-tsars-secret-police-birth-russias-deep-state-sula-hqstf/",
    "https://www.linkedin.com/pulse/part-2-c2-series-foundations-real-multi-domain-operations-eva-sula-o3qmf/",
    "https://www.linkedin.com/pulse/governance-defence-rules-realities-non-negotiables-intro-eva-sula-v0rvf/",
    # --- Second batch (29 new articles, 1 duplicate removed) ---
    "https://www.linkedin.com/pulse/part-1-governance-defence-nato-gatekeeping-assurance-eva-sula-wkl8f/",
    "https://www.linkedin.com/pulse/part-6-cyber-before-tanks-hybrid-doctrine-action-eva-sula-3jnvf/",
    "https://www.linkedin.com/pulse/part-4-c2-miniseries-people-policy-process-core-blockers-eva-sula-qdqif/",
    "https://www.linkedin.com/pulse/autonomy-defence-part-2-backbone-bust-from-expensive-eva-sula-okglf/",
    "https://www.linkedin.com/pulse/governance-defence-part-2-iso-standards-backbone-credibility-sula-inqsf/",
    "https://www.linkedin.com/pulse/ai-defence-part-6-without-trust-fails-eva-sula-mb1df/",
    "https://www.linkedin.com/pulse/security-cyber-defence-beyond-illusion-safety-part-2-eva-sula-1ay1f/",
    "https://www.linkedin.com/pulse/part-7-russkiy-mir-empire-logic-worldview-shapes-behaviour-eva-sula-terhf/",
    "https://www.linkedin.com/pulse/governance-defence-part-3-esg-ethics-culture-trust-eva-sula-nrx3c/",
    "https://www.linkedin.com/pulse/ai-defence-part-7-command-responsibility-where-line-eva-sula-l1uaf/",
    "https://www.linkedin.com/pulse/autonomy-defence-part-3-c2-age-delegation-authority-eva-sula-j15ec/",
    "https://www.linkedin.com/pulse/part-5-c2-miniseries-how-prepare-article-10-days-3-months-eva-sula-mxnfc/",
    "https://www.linkedin.com/pulse/finlands-blind-spot-how-one-cultural-pattern-undermines-eva-sula-sh90f/",
    "https://www.linkedin.com/pulse/security-cyber-defence-beyond-illusion-safety-part-3-eva-sula-0qgdf/",
    "https://www.linkedin.com/pulse/part-8-from-understanding-action-what-russkiy-mir-demands-eva-sula-bnpsf/",
    "https://www.linkedin.com/pulse/c2-mini-series-part-6-integrated-balticarctic-deterrence-eva-sula-dgouf/",
    "https://www.linkedin.com/pulse/governance-defence-part-4-gdpr-personal-data-why-national-eva-sula-stsaf/",
    "https://www.linkedin.com/pulse/autonomy-defence-part-4-ew-contested-reality-why-labs-eva-sula-pjztf/",
    "https://www.linkedin.com/pulse/russia-active-measures-mini-series-part-1-what-actually-eva-sula-mc51f/",
    "https://www.linkedin.com/pulse/governance-defence-part-5-nis2-supply-chain-integrity-eva-sula-j8msf/",
    "https://www.linkedin.com/pulse/autonomy-defence-beyond-drone-part-5-hidden-war-data-eva-sula-tlvzf/",
    "https://www.linkedin.com/pulse/defence-capability-layers-mini-series-layer-1-political-eva-sula-0jk5f/",
    "https://www.linkedin.com/pulse/c2-miniseries-part-7-commander-modern-technology-tool-eva-sula-mce1f/",
    "https://www.linkedin.com/pulse/security-cyber-defence-beyond-illusion-safety-part-4-eva-sula-yrfaf/",
    "https://www.linkedin.com/pulse/autonomy-defence-beyond-drone-part-6-integration-real-eva-sula-mmssf/",
    "https://www.linkedin.com/pulse/defence-capability-layers-layer-2-structures-doctrine-eva-sula-e1vyf/",
    "https://www.linkedin.com/pulse/c2-miniseries-part-8-backbone-bust-architecture-decision-eva-sula-ikp7f/",
    "https://www.linkedin.com/pulse/security-cyber-defence-beyond-illusion-safety-part-5-eva-sula-ajtlf/",
    "https://www.linkedin.com/pulse/finlands-defence-strength-real-so-blind-spots-eva-sula-qhvyf/",
    "https://www.linkedin.com/pulse/ai-defence-part-9-governance-accountability-eva-sula-bphhf/",
    # --- Third batch (24 new articles) ---
    "https://www.linkedin.com/pulse/c2-miniseries-part-12-stakes-deterrence-vs-delay-eva-sula-r2kxf/",
    "https://www.linkedin.com/pulse/defence-capability-layers-layer-7-culture-silent-glue-eva-sula-q6muf/",
    "https://www.linkedin.com/pulse/autonomy-defence-beyond-drone-part-11-capability-human-eva-sula-paydf/",
    "https://www.linkedin.com/pulse/european-reality-capability-unity-illusion-control-part-eva-sula-ughtf/",
    "https://www.linkedin.com/pulse/cognitive-warfare-part-3-attack-chain-how-works-eva-sula-jxjef/",
    "https://www.linkedin.com/pulse/governance-defence-part-11-ai-governance-decision-integrity-eva-sula-ve6if/",
    "https://www.linkedin.com/pulse/when-drones-cross-borders-what-estonia-finlands-response-eva-sula-nwqof/",
    "https://www.linkedin.com/pulse/lessons-from-ukraine-part-3-side-adapts-fastest-survives-eva-sula-vwkdf/",
    "https://www.linkedin.com/pulse/mdo-from-domains-delivery-part-3-air-superiority-contested-eva-sula-zad3f/",
    "https://www.linkedin.com/pulse/russia-active-measures-mini-series-part-7-defence-response-sula-kcjbf/",
    "https://www.linkedin.com/pulse/beyond-procurement-real-challenge-making-capability-work-eva-sula-f6o7f/",
    "https://www.linkedin.com/pulse/ai-defence-part-15-autonomy-delegation-command-age-eva-sula-13bzf/",
    "https://www.linkedin.com/pulse/security-cyber-defence-beyond-illusion-safety-part-10-eva-sula-ipbxf/",
    "https://www.linkedin.com/pulse/irregular-foundations-part-ii-new-kill-zone-persistent-eva-sula-0mbff/",
    "https://www.linkedin.com/pulse/planning-baltic-sea-system-part-2-map-maritime-just-eva-sula-tassf/",
    "https://www.linkedin.com/pulse/c2-miniseries-part-14-trust-political-societal-deterrence-eva-sula-asuhf/",
    "https://www.linkedin.com/pulse/defence-capability-layers-closing-gap-between-systems-eva-sula-iwctf/",
    "https://www.linkedin.com/pulse/autonomy-defence-beyond-drone-part-12-sustainment-winning-eva-sula-iieif/",
    "https://www.linkedin.com/pulse/european-reality-capability-unity-illusion-control-part-eva-sula-y8kvf/",
    "https://www.linkedin.com/pulse/cognitive-warfare-part-4-toolbox-what-methods-used-eva-sula-w039f/",
    "https://www.linkedin.com/pulse/part-12-governance-autonomous-lethal-systems-control-eva-sula-2wycf/",
    "https://www.linkedin.com/pulse/lessons-from-ukraine-part-4-drones-platforms-eva-sula-ohyxf/",
    "https://www.linkedin.com/pulse/russia-active-measures-mini-series-part-8-leadership-eva-sula-2y8uf/",
    "https://www.linkedin.com/pulse/mdo-from-domains-delivery-part-4-space-invisible-backbone-eva-sula-kanof/",
]

OUTPUT_FILE = r"D:\Ananta Meridian\Data fusion_Claude\eva_sula_articles_dump.txt"


def fetch_article(url: str) -> str:
    try:
        import requests
        from html.parser import HTMLParser

        class TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.text = []
                self.skip = False

            def handle_starttag(self, tag, attrs):
                if tag in ("script", "style", "nav", "header", "footer"):
                    self.skip = True

            def handle_endtag(self, tag):
                if tag in ("script", "style", "nav", "header", "footer"):
                    self.skip = False

            def handle_data(self, data):
                if not self.skip and data.strip():
                    self.text.append(data.strip())

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            parser = TextExtractor()
            parser.feed(response.text)
            text = " ".join(parser.text)
            # Clean up whitespace
            import re
            text = re.sub(r'\s+', ' ', text).strip()
            return text[:5000]  # First 5000 chars per article
        else:
            return f"[BLOCKED: HTTP {response.status_code} — LinkedIn requires login for this content]"

    except Exception as e:
        return f"[ERROR: {str(e)}]"


def main():
    print(f"Fetching {len(URLS)} articles...")
    print(f"Output: {OUTPUT_FILE}\n")

    results = []

    for i, url in enumerate(URLS):
        slug = url.split("/pulse/")[1].split("/")[0]
        print(f"[{i+1}/{len(URLS)}] {slug[:60]}...")

        content = fetch_article(url)
        status = "OK" if not content.startswith("[") else "XX"
        print(f"  {status} {len(content)} chars")

        results.append({
            "url": url,
            "slug": slug,
            "content": content
        })

        time.sleep(2)  # Be respectful to LinkedIn servers

    # Write dump file
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("EVA SULA ARTICLES DUMP\n")
        f.write("=" * 60 + "\n")
        f.write(f"Total articles: {len(results)}\n")
        f.write("=" * 60 + "\n\n")

        for r in results:
            f.write(f"\n{'='*60}\n")
            f.write(f"URL: {r['url']}\n")
            f.write(f"SLUG: {r['slug']}\n")
            f.write(f"{'='*60}\n")
            f.write(r['content'])
            f.write("\n")

    print(f"\nDone. Dump saved to:\n{OUTPUT_FILE}")
    print("\nShare the file path with Claude to read all articles at once.")


if __name__ == "__main__":
    main()
