import React, { useState } from 'react';
import heartSvg from '../assets/figma/heart.svg';
import messageSvg from '../assets/figma/message.svg';

export interface PostCardProps {
  id?: string;
  title: string;
  content: string;
  author: string;
  authorAvatar?: string;
  createdAt: string;
  category?: string;
  viewCount?: number;
  commentCount?: number;
  likeCount?: number;
  hasCounterclaim?: boolean;
  onClick?: () => void;
}

export const PostCard: React.FC<PostCardProps> = ({
  title,
  content,
  author,
  createdAt,
  category = '영화 분석',
  commentCount = 0,
  likeCount = 0,
  onClick
}) => {
  return (
    <div
      className="post-card-container"
      onClick={onClick}
      style={{
        background: '#FFFFFF',
        border: '1px solid #EEEEEE',
        borderRadius: '12px',
        padding: '24px',
        cursor: 'pointer',
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
        transition: 'all 0.2s ease',
        boxShadow: '0 2px 6px #00000008'
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = '#4C22F440';
        e.currentTarget.style.boxShadow = '0 6px 16px #00000010';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = '#EEEEEE';
        e.currentTarget.style.boxShadow = '0 2px 6px #00000008';
      }}
    >
      {/* Header with category and timestamp */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{
          fontSize: '12px',
          fontWeight: 700,
          color: '#4C22F4',
          background: '#F0EDFF',
          padding: '4px 10px',
          borderRadius: '9999px',
        }}>
          {category}
        </span>
        <span style={{ fontSize: '13px', color: '#888888' }}>{createdAt}</span>
      </div>

      {/* Post Title */}
      <h3 style={{
        fontSize: '18px',
        fontWeight: 700,
        color: '#2D2D34',
        margin: 0,
        lineHeight: 1.4
      }}>
        {title}
      </h3>

      {/* Preview Content */}
      <p style={{
        fontSize: '14px',
        color: '#555555',
        lineHeight: 1.6,
        margin: 0,
        display: '-webkit-box',
        WebkitLineClamp: 2,
        WebkitBoxOrient: 'vertical',
        overflow: 'hidden'
      }}>
        {content}
      </p>

      {/* Footer: Author info & reaction stats */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingTop: '12px',
        borderTop: '1px solid #EEEEEE',
        fontSize: '13px',
        color: '#888888'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div className="post-card-avatar" style={{
            width: '24px',
            height: '24px',
            borderRadius: '50%',
            background: '#4C22F420',
            color: '#4C22F4',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '12px',
            fontWeight: 700
          }}>
            {author.slice(0, 1).toUpperCase()}
          </div>
          <span style={{ fontWeight: 600, color: '#2D2D34' }}>{author}</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <img src={messageSvg} alt="" style={{ width: '14px', height: '14px', opacity: 0.6 }} />
            <span>{commentCount}</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <img src={heartSvg} alt="" style={{ width: '14px', height: '14px', opacity: 0.6 }} />
            <span>{likeCount}</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export interface CounterclaimCardProps {
  id?: string;
  claimant: string;
  argument: string;
  confidence?: number;
  agreeCount?: number;
  disagreeCount?: number;
  onVoteAgree?: () => void;
  onVoteDisagree?: () => void;
}

export const CounterclaimCard: React.FC<CounterclaimCardProps> = ({
  claimant,
  argument,
  agreeCount = 0,
  disagreeCount = 0,
  onVoteAgree,
  onVoteDisagree
}) => {
  const [userVote, setUserVote] = useState<'agree' | 'disagree' | null>(null);
  const [agrees, setAgrees] = useState(agreeCount);
  const [disagrees, setDisagrees] = useState(disagreeCount);

  const handleAgree = () => {
    if (userVote === 'agree') {
      setUserVote(null);
      setAgrees(agrees - 1);
    } else {
      if (userVote === 'disagree') setDisagrees(disagrees - 1);
      setUserVote('agree');
      setAgrees(agrees + 1);
      onVoteAgree?.();
    }
  };

  const handleDisagree = () => {
    if (userVote === 'disagree') {
      setUserVote(null);
      setDisagrees(disagreeCount - 1);
    } else {
      if (userVote === 'agree') setAgrees(agrees - 1);
      setUserVote('disagree');
      setDisagrees(disagreeCount + 1);
      onVoteDisagree?.();
    }
  };

  return (
    <div style={{
      background: '#F8F9FA',
      border: '1px solid #E5E5E5',
      borderRadius: '8px',
      padding: '16px 20px',
      display: 'flex',
      flexDirection: 'column',
      gap: '10px'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: '13px', fontWeight: 700, color: '#4C22F4' }}>
          반론 주장
        </span>
        <span style={{ fontSize: '12px', color: '#888888' }}>by {claimant}</span>
      </div>

      <p style={{ fontSize: '14px', color: '#2D2D34', lineHeight: 1.5, margin: 0 }}>
        {argument}
      </p>

      {/* Vote Buttons */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', paddingTop: '6px' }}>
        <button
          onClick={handleAgree}
          style={{
            padding: '6px 14px',
            borderRadius: '6px',
            background: userVote === 'agree' ? '#E8F5E9' : '#FFFFFF',
            border: userVote === 'agree' ? '1px solid #27AE60' : '1px solid #E5E5E5',
            color: userVote === 'agree' ? '#27AE60' : '#555555',
            fontSize: '13px',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          동의 {agrees}
        </button>

        <button
          onClick={handleDisagree}
          style={{
            padding: '6px 14px',
            borderRadius: '6px',
            background: userVote === 'disagree' ? '#FFEBEE' : '#FFFFFF',
            border: userVote === 'disagree' ? '1px solid #EB5757' : '1px solid #E5E5E5',
            color: userVote === 'disagree' ? '#EB5757' : '#555555',
            fontSize: '13px',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          비동의 {disagrees}
        </button>
      </div>
    </div>
  );
};
