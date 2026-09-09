import React, { useState } from 'react';
import { isVisualFixtureMode } from '../testing/useVisualFixture';
import { LiveCommunityPage } from './LiveCommunityPage';

interface CommunityPageProps {
  cardCount?: number;
  navigate: (path: string) => void;
}

export const CommunityPage: React.FC<CommunityPageProps> = ({ cardCount = 4, navigate }) => {
  const [selectedCategory, setSelectedCategory] = useState(0);
  const [sort, setSort] = useState<'latest' | 'popular' | 'views'>('latest');

  const categories = ['카테고리', '카테고리', '카테고리', '카테고리', '카테고리', '카테고리', '카테고리', '카테고리', '카테고리', '카테고리'];
  const items = Array.from({ length: cardCount }, (_, i) => i);

  const isTopicPage = cardCount === 3;

  if (!isVisualFixtureMode()) return <LiveCommunityPage navigate={navigate} />;

  return (
    <div data-layer="커뮤니티" style={{ width: 1920, position: 'relative', background: 'var(--Gray-0, white)', flexDirection: 'column', display: 'flex' }}>
      <div data-layer="Frame 2147227294" style={{ alignSelf: 'stretch', paddingTop: 20, flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', display: 'flex' }}>
        {/* Category Chips Bar (1:1 Figma Frame 2147227287) */}
        <div data-layer="Frame 2147227287" style={{ alignSelf: 'stretch', paddingLeft: 120, paddingRight: 120, paddingTop: 20, paddingBottom: 20, justifyContent: 'flex-start', alignItems: 'flex-start', gap: 24, display: 'inline-flex' }}>
          {categories.map((cat, idx) => (
            <div
              key={idx}
              onClick={() => setSelectedCategory(idx)}
              data-layer="CategoryChip"
              data-state={selectedCategory === idx ? 'Pressed' : 'Default'}
              style={{
                flex: '1 1 0',
                height: 44,
                boxSizing: 'border-box',
                paddingLeft: 14,
                paddingRight: 14,
                paddingTop: 10,
                paddingBottom: 10,
                background: selectedCategory === idx ? 'var(--Gray-700, #4A4A53)' : 'var(--Gray-100, #F2F2F5)',
                borderRadius: 20,
                justifyContent: 'center',
                alignItems: 'center',
                gap: 4,
                display: 'flex',
                cursor: 'pointer'
              }}
            >
              <div data-layer="Applied Tag Container" style={{ justifyContent: 'flex-start', alignItems: 'center', gap: 4, display: 'flex' }}>
                <div data-layer="Text" style={{ textAlign: 'center', color: selectedCategory === idx ? 'var(--Gray-0, white)' : 'var(--Gray-700, #4A4A53)', fontSize: 20, fontFamily: 'Pretendard', fontWeight: '500', lineHeight: '24px', wordWrap: 'break-word' }}>
                  {cat}
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Filter Row (1:1 Figma Frame 2147227218) */}
        <div data-layer="Frame 2147227218" style={{ alignSelf: 'stretch', height: 61, boxSizing: 'border-box', paddingLeft: 120, paddingRight: 120, paddingTop: 20, paddingBottom: 20, borderBottom: '1px var(--Gray-100, #F2F2F5) solid', justifyContent: 'space-between', alignItems: 'center', display: 'inline-flex' }}>
          <div data-layer="총 29개" style={{ color: 'var(--Gray-800, #2D2D34)', fontSize: 18, fontFamily: 'Pretendard', fontWeight: '600', lineHeight: '21px', wordWrap: 'break-word' }}>
            총 29개
          </div>
          <div data-layer="Frame 2147227219" style={{ justifyContent: 'flex-start', alignItems: 'center', gap: 10, display: 'flex' }}>
            <div
              onClick={() => setSort('latest')}
              data-layer="최신순"
              style={{ color: sort === 'latest' ? 'var(--Gray-800, #2D2D34)' : 'var(--Gray-500, #898992)', fontSize: 16, fontFamily: 'Pretendard', fontWeight: '400', lineHeight: '20px', wordWrap: 'break-word', cursor: 'pointer' }}
            >
              최신순
            </div>
            <div
              onClick={() => setSort('popular')}
              data-layer="인기순"
              style={{ color: sort === 'popular' ? 'var(--Gray-800, #2D2D34)' : 'var(--Gray-500, #898992)', fontSize: 16, fontFamily: 'Pretendard', fontWeight: '400', lineHeight: '20px', wordWrap: 'break-word', cursor: 'pointer' }}
            >
              인기순
            </div>
            <div
              onClick={() => setSort('views')}
              data-layer="조회수"
              style={{ color: sort === 'views' ? 'var(--Gray-800, #2D2D34)' : 'var(--Gray-500, #898992)', fontSize: 16, fontFamily: 'Pretendard', fontWeight: '400', lineHeight: '20px', wordWrap: 'break-word', cursor: 'pointer' }}
            >
              조회수
            </div>
          </div>
        </div>

        {/* Post Items List (1:1 Figma Frame 2147227211 / Frame 2147227195 / Frame 2147227293) */}
        <div data-layer="Frame 2147227211" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', display: 'flex' }}>
          <div data-layer="Frame 2147227195" style={{ alignSelf: 'stretch', paddingLeft: isTopicPage ? 191 : 120, paddingRight: isTopicPage ? 191 : 120, paddingTop: isTopicPage ? 67 : 40, paddingBottom: isTopicPage ? 30 : 40, flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', display: 'flex' }}>
            <div data-layer="Frame 2147227293" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: isTopicPage ? 60 : 32, display: 'flex' }}>
              {items.map((idx) => (
                <div
                  key={idx}
                  onClick={() => navigate('/posts/post_001')}
                  data-layer={`Frame 214722717${9 + idx}`}
                  style={{ alignSelf: 'stretch', height: 180, boxSizing: 'border-box', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 20, display: 'inline-flex', cursor: 'pointer' }}
                >
                  <div data-layer="Frame 2147227177" style={{ flex: '1 1 0', alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'space-between', alignItems: 'flex-start', display: 'inline-flex' }}>
                    <div data-layer="Frame 2147227292" style={{ alignSelf: 'stretch', flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 16, display: 'flex' }}>
                      <div data-layer="카테고리" style={{ alignSelf: 'stretch', justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Purple-500, #4C22F4)', fontSize: 16, fontFamily: 'Pretendard', fontWeight: '500', wordWrap: 'break-word' }}>
                        카테고리
                      </div>
                      <div data-layer="Frame 2147227291" style={{ flexDirection: 'column', justifyContent: 'flex-start', alignItems: 'flex-start', gap: 8, display: 'flex' }}>
                        <div data-layer="제목을 한줄로 구성해서 적어주세요." style={{ justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-800, #2D2D34)', fontSize: 18, fontFamily: 'Pretendard', fontWeight: '600', lineHeight: '27px', wordWrap: 'break-word' }}>
                          제목을 한줄로 구성해서 적어주세요.
                        </div>
                        <div data-layer="해당 콘텐츠에 대한 내용을 적어주세요. 최대 2줄로 구성해주세요." style={{ justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-800, #2D2D34)', fontSize: 14, fontFamily: 'Pretendard', fontWeight: '400', lineHeight: '21px', wordWrap: 'break-word' }}>
                          해당 콘텐츠에 대한 내용을 적어주세요.<br />최대 2줄로 구성해주세요.
                        </div>
                      </div>
                    </div>
                    <div data-layer="Frame 2147227285" style={{ justifyContent: 'flex-start', alignItems: 'flex-start', gap: 13, display: 'inline-flex' }}>
                      <div data-layer="Frame 2147227210" style={{ justifyContent: 'flex-start', alignItems: 'flex-start', gap: 4, display: 'flex' }}>
                        <div data-layer="eye" style={{ width: 16, height: 16, position: 'relative', overflow: 'hidden' }}>
                          <svg width="100%" height="100%" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path d="M1.61342 8.4761C1.52262 8.33234 1.47723 8.26046 1.45182 8.1496C1.43273 8.06632 1.43273 7.93498 1.45182 7.85171C1.47723 7.74084 1.52262 7.66896 1.61341 7.5252C2.36369 6.33721 4.59693 3.33398 8.00027 3.33398C11.4036 3.33398 13.6369 6.33721 14.3871 7.5252C14.4779 7.66896 14.5233 7.74084 14.5487 7.85171C14.5678 7.93498 14.5678 8.06632 14.5487 8.1496C14.5233 8.26046 14.4779 8.33234 14.3871 8.4761C13.6369 9.66409 11.4036 12.6673 8.00027 12.6673C4.59693 12.6673 2.36369 9.66409 1.61342 8.4761Z" stroke="var(--Gray-400, #AFAFB8)" strokeWidth="1.33333" strokeLinecap="round" strokeLinejoin="round" />
                            <path d="M8.00027 10.0007C9.10484 10.0007 10.0003 9.10522 10.0003 8.00065C10.0003 6.89608 9.10484 6.00065 8.00027 6.00065C6.8957 6.00065 6.00027 6.89608 6.00027 8.00065C6.00027 9.10522 6.8957 10.0007 8.00027 10.0007Z" stroke="var(--Gray-400, #AFAFB8)" strokeWidth="1.33333" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                        </div>
                        <div data-layer="1,643" style={{ justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-500, #898992)', fontSize: 12, fontFamily: 'Pretendard', fontWeight: '400', wordWrap: 'break-word' }}>
                          1,643
                        </div>
                      </div>
                      <div data-layer="Frame 2147227211" style={{ justifyContent: 'flex-start', alignItems: 'flex-start', gap: 4, display: 'flex' }}>
                        <div data-layer="heart" style={{ width: 16, height: 16, position: 'relative', overflow: 'hidden' }}>
                          <svg width="100%" height="100%" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path fillRule="evenodd" clipRule="evenodd" d="M7.99511 3.42388C6.66221 1.8656 4.43951 1.44643 2.76947 2.87334C1.09944 4.30026 0.86432 6.68598 2.17581 8.3736C3.26622 9.77674 6.56619 12.7361 7.64774 13.6939C7.76874 13.801 7.82925 13.8546 7.89982 13.8757C7.96141 13.8941 8.02881 13.8941 8.0904 13.8757C8.16097 13.8546 8.22147 13.801 8.34248 13.6939C9.42403 12.7361 12.724 9.77674 13.8144 8.3736C15.1259 6.68598 14.9195 4.28525 13.2207 2.87334C11.522 1.46144 9.32801 1.8656 7.99511 3.42388Z" stroke="var(--Gray-400, #AFAFB8)" strokeWidth="1.33333" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                        </div>
                        <div data-layer="1,643" style={{ justifyContent: 'center', display: 'flex', flexDirection: 'column', color: 'var(--Gray-500, #898992)', fontSize: 12, fontFamily: 'Pretendard', fontWeight: '400', wordWrap: 'break-word' }}>
                          1,643
                        </div>
                      </div>
                    </div>
                  </div>
                  {!isTopicPage && <div data-layer="Rectangle 240655222" style={{ width: 180, height: 180, background: '#D9D9D9', borderRadius: 12 }} />}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
