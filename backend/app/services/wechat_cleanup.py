"""Remove original collection assets when their indexed document is deleted."""

from app.models.wechat_knowledge import WeChatKnowledgeItem
from app.services.document_processor import document_processor


async def delete_collection_originals(document) -> None:
    metadata = document.metadata or {}
    if metadata.get("source") != "wechat":
        return
    rows = await WeChatKnowledgeItem.filter(document_id=document.id)
    for item in rows:
        if item.original_path:
            expected = (
                f"documents/{document.knowledge_base_id}/wechat/{item.id}/original/"
            )
            if item.original_path.startswith(expected):
                await document_processor.delete_file(item.original_path)
            item.original_path = None
            await item.save(update_fields=["original_path"])
    # Receipt results are historical; the download endpoint still verifies the
    # current item path, so it cannot serve a deleted original from a stale UI.
