"""Collapsed review counts include masked replies, not deleted/removed content."""
import json
import uuid

import pytest
from src.reframe.community.models import Comment, Post, PostVersion
from src.reframe.community.service import CommunityService
from src.reframe.identity.auth import ViewerContext
from src.reframe.identity.models import User
from src.reframe.shared.database import AsyncSessionLocal


@pytest.mark.asyncio
@pytest.mark.parametrize('root_status,reply_status,expected', [
    ('PUBLISHED', 'PUBLISHED', 2), ('DELETED', 'PUBLISHED', 1),
    ('REMOVED', 'PUBLISHED', 0), ('DRAFT', 'PUBLISHED', 0),
    ('PUBLISHED', 'DELETED', 1), ('PUBLISHED', 'REMOVED', 1),
    ('PUBLISHED', 'DRAFT', 1),
])
@pytest.mark.parametrize('masked_review', [False, True])
async def test_review_list_has_count_before_thread_is_opened(root_status, reply_status, expected, masked_review):
    work = 'count-' + uuid.uuid4().hex
    async with AsyncSessionLocal() as db:
        owner = User(id=uuid.uuid4(), email_normalized=f'{uuid.uuid4()}@example.test')
        db.add(owner)
        await db.flush()
        posts = []
        for _ in range(2):
            post = Post(id=uuid.uuid4(), author_id=owner.id, work_id=work, edition_id='test', status='PUBLISHED', content_type='REVIEW')
            db.add(post)
            await db.flush()
            version = PostVersion(id=uuid.uuid4(), post_id=post.id, created_by=owner.id,
                title='Test review', body_markdown='Review text', body_sanitized_html='<p>Review text</p>',
                contains_spoilers=masked_review, inspection_status='VERIFIED')
            db.add(version)
            await db.flush()
            post.current_version_id = version.id
            posts.append(post)
        root = Comment(id=uuid.uuid4(), post_id=posts[0].id, author_id=owner.id,
            body_markdown='SECRET_COMMENT_BODY', body_sanitized_html='<p>SECRET_COMMENT_BODY</p>',
            contains_spoilers=True, status=root_status)
        db.add(root)
        await db.flush()
        reply = Comment(id=uuid.uuid4(), post_id=posts[0].id, parent_comment_id=root.id, author_id=owner.id,
            body_markdown='SECRET_REPLY_BODY', body_sanitized_html='<p>SECRET_REPLY_BODY</p>',
            contains_spoilers=True, status=reply_status)
        db.add(reply)
        await db.commit()
        viewer = ViewerContext()
        result = await CommunityService.list_posts(db, viewer, work_id=work)
        by_id = {p['post_id']:p for p in result}
        assert by_id[str(posts[0].id)]['comments_count'] == expected
        assert by_id[str(posts[1].id)]['comments_count'] == 0
        assert by_id[str(posts[0].id)]['is_spoiler_masked'] == masked_review
        assert 'SECRET_' not in json.dumps(result)
        visible = await CommunityService.list_comments(db, posts[0].id, viewer)
        assert expected == len([c for c in visible if c['status'] != 'DELETED'])
