"""批量上传 zequant 策略实现的 README.md（以策略名.md 命名）"""
import asyncio
import glob
from pathlib import Path
from app.services.document_service import DocumentService
from app.services.pipeline_service import IngestionPipeline
from app.models.document import DocumentCreate, DocumentMetadata


async def main():
    ds = DocumentService()
    p = IngestionPipeline()

    impl_dir = "/Users/wangzeshang1/MyProjects/zequant/core/strategies/impl"
    readmes = sorted(glob.glob(f"{impl_dir}/*/README.md"))
    # 排除 _template
    readmes = [r for r in readmes if "/_template/" not in r]
    
    print(f"找到 {len(readmes)} 个策略 README\n")

    for filepath in readmes:
        strategy_name = Path(filepath).parent.name
        filename = f"{strategy_name}.md"
        print(f"{'='*60}")
        print(f"上传: {filename}")

        with open(filepath, 'r') as f:
            content = f.read()

        doc = await ds.create_document(DocumentCreate(
            filename=filename,
            content=content,
            metadata=DocumentMetadata(title=filename)
        ))
        print(f"  doc_id: {doc.id}")

        report = await p.run(doc_ids=[doc.id])
        r = report.results[0]
        print(f"  status: {r.status} | merge_type: {r.merge_type}")
        print(f"  changes: {r.changes[:2]}")
        if r.error:
            print(f"  ERROR: {r.error}")
        print()

    # 最终结果
    print(f"\n{'='*60}")
    print("最终 Wiki 页面:")
    from app.services.wiki_service import WikiService
    ws = WikiService()
    pages = await ws.list_pages()
    for page in pages:
        print(f"  - [{page.id}] {page.metadata.title} (v{page.metadata.version}, sources: {len(page.metadata.source_documents)})")
    print(f"\n共 {len(pages)} 个 Wiki 页面")

asyncio.run(main())