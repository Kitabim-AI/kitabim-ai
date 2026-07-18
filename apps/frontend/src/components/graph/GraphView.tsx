import React, { useEffect, useState, useRef, useMemo } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { useI18n } from '../../i18n/I18nContext';
import { useTheme } from '../../context/ThemeContext';
import { useAppContext } from '../../context/AppContext';
import { useNotification } from '../../context/NotificationContext';
import { useIsAdmin } from '../../hooks/useAuth';
import { authFetch } from '../../services/authService';
import { Search, Loader2, ZoomIn, ZoomOut, Maximize, Minimize, Maximize2, Network, BookOpen, MapPin, User, Calendar, HelpCircle, X, SlidersHorizontal, Building, Clock, Lightbulb, ChevronDown, Trash2, GitMerge } from 'lucide-react';

interface GraphNode {
  id: string;
  label: string;
  type: string;
  x?: number;
  y?: number;
  color?: string;
  year_hijri?: number;
  year_gregorian?: number;
  century_gregorian?: number;
}

interface GraphLink {
  source: any;
  target: any;
  label: string;
  year_hijri?: number;
  year_gregorian?: number;
  century_gregorian?: number;
}

interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

const formatCentury = (century: number, lang: string) => {
  if (lang === 'ug') {
    return `${century}-ئەسىر`;
  }
  const suffix = (c: number) => {
    if (c > 3 && c < 21) return 'th';
    switch (c % 10) {
      case 1:  return "st";
      case 2:  return "nd";
      case 3:  return "rd";
      default: return "th";
    }
  };
  return `${century}${suffix(century)} Century`;
};

const formatYear = (year: number, type: 'hijri' | 'gregorian', lang: string) => {
  if (lang === 'ug') {
    return type === 'hijri' ? `${year}-يىلى (ھ)` : `${year}-يىلى (م)`;
  }
  return type === 'hijri' ? `${year} AH` : `${year} CE`;
};

export const GraphView: React.FC = () => {
  const { t, language } = useI18n();
  const { theme } = useTheme();
  const isThemeDark = theme === 'dark';
  const isAdmin = useIsAdmin();
  const { setModal } = useAppContext();
  const { addNotification } = useNotification();
  const [rawGraphData, setRawGraphData] = useState<GraphData>({ nodes: [], links: [] });
  const [selectedNodeTypes, setSelectedNodeTypes] = useState<string[]>([]);
  const [selectedEdgeTypes, setSelectedEdgeTypes] = useState<string[]>([]);
  const [activeTab, setActiveTab] = useState<'details' | 'filters'>('filters');
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [nodeConnections, setNodeConnections] = useState<any[]>([]);
  const [showMobileFilters, setShowMobileFilters] = useState(false);
  const [showLegend, setShowLegend] = useState(window.innerWidth >= 768);
  const [isFullScreen, setIsFullScreen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<any>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });

  // Automatically switch tab to Details when a node is selected
  useEffect(() => {
    if (selectedNode) {
      setActiveTab('details');
    }
  }, [selectedNode]);

  // Load graph data
  const fetchGraphData = async (query = '') => {
    setLoading(true);
    try {
      const res = await fetch(`/api/books/graph${query ? `?q=${encodeURIComponent(query)}` : ''}`);
      const graphData: GraphData = await res.json();

      // Color-code the nodes based on type
      const coloredNodes = graphData.nodes.map(node => {
        let color = '#94a3b8'; // Default slate
        const type = (node.type || '').toLowerCase();
        if (type.includes('person') || type.includes('character') || type.includes('يازغۇچى') || type.includes('شەخس')) {
          color = '#fbbf24'; // Amber
        } else if (type.includes('place') || type.includes('location') || type.includes('يەر') || type.includes('جاھان')) {
          color = '#38bdf8'; // Sky Blue
        } else if (type.includes('org') || type.includes('group') || type.includes('تەشكىلات')) {
          color = '#34d399'; // Emerald Green
        } else if (type.includes('event') || type.includes('تارىخ') || type.includes('ۋەقە')) {
          color = '#f87171'; // Rose
        } else if (type.includes('historicalera') || type.includes('era') || type.includes('دەۋر')) {
          color = '#c084fc'; // Purple
        } else if (type.includes('concept') || type.includes('ئۇقۇم')) {
          color = '#818cf8'; // Indigo
        } else if (type.includes('other') || type.includes('باشقىلار')) {
          color = '#94a3b8'; // Slate
        } else if (type.includes('book') || type.includes('ئەسەر') || type.includes('قىسسە')) {
          color = '#818cf8'; // Map legacy book to indigo (concept)
        }
        return { ...node, color };
      });

      setRawGraphData({ nodes: coloredNodes, links: graphData.links });

      // Initialize selected types to all unique types
      const uniqueNodeTypes = Array.from(new Set(coloredNodes.map(node => node.type || 'Entity')));
      const uniqueEdgeTypes = Array.from(new Set(graphData.links.map(link => link.label || 'RELATED_TO')));
      setSelectedNodeTypes(uniqueNodeTypes);
      setSelectedEdgeTypes(uniqueEdgeTypes);
    } catch (e) {
      console.error('Failed to load graph data', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchGraphData();
  }, []);

  // Extract all unique available node and edge types from raw data
  const availableNodeTypes = useMemo(() => {
    return Array.from(new Set(rawGraphData.nodes.map(node => node.type || 'Entity')));
  }, [rawGraphData]);

  const availableEdgeTypes = useMemo(() => {
    return Array.from(new Set(rawGraphData.links.map(link => link.label || 'RELATED_TO')));
  }, [rawGraphData]);

  // Compute filtered graph data based on selected filters
  const filteredData = useMemo(() => {
    const filteredNodes = rawGraphData.nodes.filter(node =>
      selectedNodeTypes.includes(node.type || 'Entity')
    );

    const filteredNodeIds = new Set(filteredNodes.map(n => n.id));

    const filteredLinks = rawGraphData.links.filter(link => {
      const linkLabel = link.label || 'RELATED_TO';
      if (!selectedEdgeTypes.includes(linkLabel)) {
        return false;
      }

      const sourceId = typeof link.source === 'object' ? link.source.id : link.source;
      const targetId = typeof link.target === 'object' ? link.target.id : link.target;
      return filteredNodeIds.has(sourceId) && filteredNodeIds.has(targetId);
    });

    return {
      nodes: filteredNodes,
      links: filteredLinks,
    };
  }, [rawGraphData, selectedNodeTypes, selectedEdgeTypes]);

  // Deselect node if it gets filtered out
  useEffect(() => {
    if (selectedNode) {
      const nodeStillExists = filteredData.nodes.some(n => n.id === selectedNode.id);
      if (!nodeStillExists) {
        setSelectedNode(null);
      }
    }
  }, [filteredData.nodes, selectedNode]);

  const toggleNodeType = (type: string) => {
    setSelectedNodeTypes(prev =>
      prev.includes(type) ? prev.filter(t => t !== type) : [...prev, type]
    );
  };

  const toggleEdgeType = (type: string) => {
    setSelectedEdgeTypes(prev =>
      prev.includes(type) ? prev.filter(t => t !== type) : [...prev, type]
    );
  };

  const getLocalizedNodeType = (type: string) => {
    const tVal = type.toLowerCase();
    if (tVal.includes('person') || tVal.includes('character') || tVal.includes('شەخس')) return language === 'ug' ? 'شەخس' : 'Person';
    if (tVal.includes('place') || tVal.includes('location') || tVal.includes('يەر')) return language === 'ug' ? 'ئورۇن' : 'Location';
    if (tVal.includes('org') || tVal.includes('group') || tVal.includes('تەشكىلات')) return language === 'ug' ? 'تەشكىلات' : 'Organization';
    if (tVal.includes('event') || tVal.includes('ۋەقە')) return language === 'ug' ? 'ۋەقە' : 'Event';
    if (tVal.includes('historicalera') || tVal.includes('era') || tVal.includes('دەۋر')) return language === 'ug' ? 'تارىخىي دەۋر' : 'Historical Era';
    if (tVal.includes('concept') || tVal.includes('ئۇقۇم')) return language === 'ug' ? 'ئۇقۇم' : 'Concept';
    if (tVal.includes('other') || tVal.includes('باشقىلار')) return language === 'ug' ? 'باشقىلار' : 'Other';
    if (tVal.includes('book') || tVal.includes('ئەسەر')) return language === 'ug' ? 'ئەسەر' : 'Book';
    return type;
  };

  const getInactiveNodeColorClass = (type: string, isDark: boolean) => {
    return isDark
      ? 'bg-slate-900/40 text-slate-500 border-slate-800 hover:text-slate-400 hover:border-slate-700'
      : 'bg-slate-50 text-slate-400 border-slate-200 hover:text-slate-600 hover:bg-slate-100 hover:border-slate-300';
  };

  const getActiveNodeColorClass = (type: string) => {
    const tVal = type.toLowerCase();
    if (tVal.includes('person') || tVal.includes('character') || tVal.includes('شەخس')) return 'bg-amber-400 text-slate-950 border-amber-500 hover:bg-amber-300';
    if (tVal.includes('place') || tVal.includes('location') || tVal.includes('يەر')) return 'bg-sky-400 text-slate-950 border-sky-500 hover:bg-sky-300';
    if (tVal.includes('org') || tVal.includes('group') || tVal.includes('تەشكىلات')) return 'bg-emerald-400 text-slate-950 border-emerald-500 hover:bg-emerald-300';
    if (tVal.includes('event') || tVal.includes('ۋەقە')) return 'bg-rose-400 text-white border-rose-500 hover:bg-rose-300';
    if (tVal.includes('historicalera') || tVal.includes('era') || tVal.includes('دەۋر')) return 'bg-purple-400 text-white border-purple-500 hover:bg-purple-300';
    if (tVal.includes('concept') || tVal.includes('ئۇقۇم')) return 'bg-indigo-400 text-white border-indigo-500 hover:bg-indigo-300';
    if (tVal.includes('other') || tVal.includes('باشقىلار')) return 'bg-slate-400 text-slate-950 border-slate-500 hover:bg-slate-300';
    if (tVal.includes('book') || tVal.includes('ئەسەر')) return 'bg-purple-400 text-white border-purple-500 hover:bg-purple-300';
    return 'bg-slate-400 text-slate-950 border-slate-500 hover:bg-slate-300';
  };

  const renderFilters = (isDark: boolean, isSidebar = false) => {
    if (availableNodeTypes.length === 0 && availableEdgeTypes.length === 0) return null;

    const activeNodeCount = selectedNodeTypes.length;
    const totalNodeTypes = availableNodeTypes.length;
    const activeEdgeCount = selectedEdgeTypes.length;
    const totalEdgeTypes = availableEdgeTypes.length;
    const isFiltered = activeNodeCount < totalNodeTypes || activeEdgeCount < totalEdgeTypes;

    const wrapperCls = isDark
      ? 'border border-slate-800 bg-slate-900/90 backdrop-blur-md rounded-2xl p-4 mt-3 flex flex-col gap-4 flex-grow min-h-0 overflow-hidden'
      : isSidebar
        ? 'border border-[#0369a1]/10 bg-white rounded-2xl shadow-md flex-grow min-h-0 flex flex-col overflow-hidden'
        : 'border border-[#0369a1]/10 bg-white rounded-2xl shadow-md p-4 mt-2 flex flex-col gap-4';

    return (
      <div className={`select-none transition-all duration-300 ${wrapperCls}`}>
        {/* Header */}
        <div
          onClick={!isSidebar ? () => setShowMobileFilters(!showMobileFilters) : undefined}
          className={`flex items-center justify-between shrink-0 ${isSidebar && !isDark ? 'px-5 pt-5' : ''} ${!isSidebar ? 'cursor-pointer hover:opacity-85 select-none' : ''}`}
        >
          <div className="flex items-center gap-2">
            <SlidersHorizontal size={13} className={isDark ? 'text-slate-400' : 'text-[#0369a1]/70'} />
            <span className={`text-xs font-bold ${isDark ? 'text-slate-200' : 'text-slate-700'}`}>
              {t('graph.tabFilters') || 'Filters'}
            </span>
            {isFiltered && (
              <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-bold leading-none ${isDark
                  ? 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
                  : 'bg-amber-50 text-amber-600 border border-amber-200'
                }`}>
                {activeNodeCount + activeEdgeCount}/{totalNodeTypes + totalEdgeTypes}
              </span>
            )}
          </div>
          {!isSidebar && (
            <div className={`transition-transform duration-300 ${showMobileFilters ? 'rotate-180' : ''}`}>
              <ChevronDown size={16} className={isDark ? 'text-slate-400' : 'text-[#0369a1]'} />
            </div>
          )}
        </div>

        {/* Scrollable filter content */}
        {(isSidebar || showMobileFilters) && (
          <div className={`flex flex-col gap-4 [scrollbar-width:thin] [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-thumb]:rounded ${isDark
              ? '[&::-webkit-scrollbar-thumb]:bg-slate-800 flex-grow min-h-0 overflow-y-auto pr-1'
              : '[&::-webkit-scrollbar-thumb]:bg-slate-200'
            } ${isSidebar && !isDark ? 'flex-grow min-h-0 overflow-y-auto px-5 pb-5' : ''}`}>

            {/* Entity Types */}
            {availableNodeTypes.length > 0 && (
              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <span className={`text-[10px] font-semibold uppercase tracking-widest ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                    {t('graph.filterNodeTypes') || 'Entity Types'}
                  </span>
                  <div className="flex items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() => setSelectedNodeTypes(availableNodeTypes)}
                      className={`text-[9px] font-semibold hover:underline transition-colors ${isDark ? 'text-sky-400 hover:text-sky-300' : 'text-[#0369a1] hover:text-[#0284c7]'
                        }`}
                    >
                      {t('graph.all') || 'All'}
                    </button>
                    <span className="text-slate-300 text-[9px] shrink-0">|</span>
                    <button
                      type="button"
                      onClick={() => setSelectedNodeTypes([])}
                      className={`text-[9px] font-semibold hover:underline transition-colors ${isDark ? 'text-rose-400 hover:text-rose-300' : 'text-rose-600 hover:text-rose-500'
                        }`}
                    >
                      {language === 'ug' ? 'ھېچقايسىسى' : 'Clear'}
                    </button>
                    <span className={`text-[10px] font-medium tabular-nums shrink-0 ml-1.5 ${activeNodeCount < totalNodeTypes
                        ? isDark ? 'text-amber-500' : 'text-amber-600'
                        : isDark ? 'text-slate-600' : 'text-slate-400'
                      }`}>
                      {activeNodeCount}/{totalNodeTypes}
                    </span>
                  </div>
                </div>
                <div className="flex flex-wrap gap-1.5 items-start">
                  {availableNodeTypes.map(type => {
                    const isActive = selectedNodeTypes.includes(type);
                    return (
                      <button
                        key={type}
                        type="button"
                        onClick={() => toggleNodeType(type)}
                        className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-xl border transition-all duration-200 active:scale-95 ${isActive
                            ? getActiveNodeColorClass(type)
                            : getInactiveNodeColorClass(type, isDark)
                          }`}
                      >
                        {getIconForType(type)}
                        <span>{getLocalizedNodeType(type)}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Divider */}
            {availableNodeTypes.length > 0 && availableEdgeTypes.length > 0 && (
              <div className={`h-px shrink-0 ${isDark ? 'bg-slate-800' : 'bg-slate-100'}`} />
            )}

            {/* Relationship Types */}
            {availableEdgeTypes.length > 0 && (
              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <span className={`text-[10px] font-semibold uppercase tracking-widest ${isDark ? 'text-slate-500' : 'text-slate-400'}`}>
                    {t('graph.filterEdgeTypes') || 'Relationship Types'}
                  </span>
                  <div className="flex items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() => setSelectedEdgeTypes(availableEdgeTypes)}
                      className={`text-[9px] font-semibold hover:underline transition-colors ${isDark ? 'text-sky-400 hover:text-sky-300' : 'text-[#0369a1] hover:text-[#0284c7]'
                        }`}
                    >
                      {t('graph.all') || 'All'}
                    </button>
                    <span className="text-slate-300 text-[9px] shrink-0">|</span>
                    <button
                      type="button"
                      onClick={() => setSelectedEdgeTypes([])}
                      className={`text-[9px] font-semibold hover:underline transition-colors ${isDark ? 'text-rose-400 hover:text-rose-300' : 'text-rose-600 hover:text-rose-500'
                        }`}
                    >
                      {language === 'ug' ? 'ھېچقايسىسى' : 'Clear'}
                    </button>
                    <span className={`text-[10px] font-medium tabular-nums shrink-0 ml-1.5 ${activeEdgeCount < totalEdgeTypes
                        ? isDark ? 'text-amber-500' : 'text-amber-600'
                        : isDark ? 'text-slate-600' : 'text-slate-400'
                      }`}>
                      {activeEdgeCount}/{totalEdgeTypes}
                    </span>
                  </div>
                </div>
                <div className="flex flex-wrap gap-1.5 items-start content-start">
                  {availableEdgeTypes.map(type => {
                    const isActive = selectedEdgeTypes.includes(type);
                    const displayName = type.replace(/_/g, ' ');
                    return (
                      <button
                        key={type}
                        type="button"
                        onClick={() => toggleEdgeType(type)}
                        className={`px-2.5 py-1 text-xs font-semibold rounded-xl border transition-all duration-200 active:scale-95 ${isActive
                            ? isDark
                              ? 'bg-indigo-500/20 text-indigo-400 border-indigo-500/40 hover:bg-indigo-500/30'
                              : 'bg-indigo-50 text-indigo-600 border-indigo-200 hover:bg-indigo-100'
                            : getInactiveNodeColorClass('other', isDark)
                          }`}
                      >
                        {displayName}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    );
  };

  useEffect(() => {
    const handleResize = () => {
      if (isFullScreen) {
        setDimensions({
          width: window.innerWidth,
          height: window.innerHeight,
        });
      } else if (containerRef.current) {
        setDimensions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight || 550,
        });
      }
    };

    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [isFullScreen]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    fetchGraphData(searchQuery);
  };

  // Escape key to exit fullscreen
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isFullScreen) {
        setIsFullScreen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isFullScreen]);

  // Prevent scroll and hide navbar when fullscreen
  useEffect(() => {
    if (isFullScreen) {
      document.body.style.overflow = 'hidden';
      document.body.classList.add('graph-fullscreen');
    } else {
      document.body.style.overflow = '';
      document.body.classList.remove('graph-fullscreen');
    }
    return () => {
      document.body.style.overflow = '';
      document.body.classList.remove('graph-fullscreen');
    };
  }, [isFullScreen]);

  // Find connections for selected node
  useEffect(() => {
    if (!selectedNode) {
      setNodeConnections([]);
      return;
    }
    const connections = filteredData.links.filter(
      link =>
        (typeof link.source === 'object' ? link.source.id : link.source) === selectedNode.id ||
        (typeof link.target === 'object' ? link.target.id : link.target) === selectedNode.id
    ).map(link => {
      const isSource = (typeof link.source === 'object' ? link.source.id : link.source) === selectedNode.id;
      const targetNodeId = isSource
        ? (typeof link.target === 'object' ? link.target.id : link.target)
        : (typeof link.source === 'object' ? link.source.id : link.source);
      const targetNode = filteredData.nodes.find(n => n.id === targetNodeId);
      return {
        label: link.label,
        direction: isSource ? 'outgoing' : 'incoming',
        node: targetNode || { id: targetNodeId, label: targetNodeId, type: 'Unknown' },
        year_hijri: link.year_hijri,
        year_gregorian: link.year_gregorian,
        century_gregorian: link.century_gregorian,
      };
    });
    setNodeConnections(connections);
  }, [selectedNode, filteredData]);

  const handleDeleteRelationship = (conn: any) => {
    if (!selectedNode) return;
    const isOutgoing = conn.direction === 'outgoing';
    const sourceName = isOutgoing ? selectedNode.id : conn.node.id;
    const targetName = isOutgoing ? conn.node.id : selectedNode.id;
    const relType = conn.label;

    setModal({
      isOpen: true,
      title: t('graph.admin.deleteRelationshipTitle'),
      message: t('graph.admin.deleteRelationshipMessage', { relType, sourceName, targetName }),
      type: 'confirm',
      destructive: true,
      confirmText: t('common.delete'),
      onConfirm: async () => {
        try {
          const res = await authFetch('/api/books/graph/relationship/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sourceName, targetName, relType }),
          });
          if (!res.ok) {
            const body = await res.json().catch(() => ({}));
            throw new Error(body.detail || t('graph.admin.deleteRelationshipError'));
          }
          setModal({ isOpen: false, title: '', message: '', type: 'alert' });
          addNotification(t('graph.admin.deleteRelationshipSuccess'), 'success');
          fetchGraphData(searchQuery);
        } catch (err: any) {
          setModal({
            isOpen: true,
            title: t('common.error'),
            message: err.message || t('graph.admin.deleteRelationshipError'),
            type: 'alert',
          });
        }
      },
    });
  };

  // Zoom helpers
  const zoomIn = () => {
    if (fgRef.current) {
      const zoom = fgRef.current.zoom();
      fgRef.current.zoom(zoom * 1.3, 400);
    }
  };

  const zoomOut = () => {
    if (fgRef.current) {
      const zoom = fgRef.current.zoom();
      fgRef.current.zoom(zoom / 1.3, 400);
    }
  };

  const resetZoom = () => {
    if (fgRef.current) {
      fgRef.current.zoomToFit(400);
    }
  };

  // Legend helper
  const getIconForType = (type: string) => {
    const t = type.toLowerCase();
    if (t.includes('person') || t.includes('character') || t.includes('شەخس')) return <User size={14} className="text-amber-400" />;
    if (t.includes('place') || t.includes('location') || t.includes('يەر')) return <MapPin size={14} className="text-sky-400" />;
    if (t.includes('org') || t.includes('group') || t.includes('تەشكىلات')) return <Building size={14} className="text-emerald-400" />;
    if (t.includes('event') || t.includes('ۋەقە')) return <Calendar size={14} className="text-rose-400" />;
    if (t.includes('historicalera') || t.includes('era') || t.includes('دەۋر')) return <Clock size={14} className="text-purple-400" />;
    if (t.includes('concept') || t.includes('ئۇقۇم')) return <Lightbulb size={14} className="text-indigo-400" />;
    if (t.includes('book') || t.includes('ئەسەر')) return <BookOpen size={14} className="text-purple-400" />;
    return <HelpCircle size={14} className="text-slate-400" />;
  };

  // Details Panel Content Renderer (Supports standard light and fullscreen dark themes)
  const renderDetailsPanelContent = (isDark: boolean) => {
    return selectedNode ? (
      <div className="h-full flex flex-col min-h-0 text-right animate-fade-in">
        <div className={`flex items-center justify-between border-b pb-4 mb-4 ${isDark ? 'border-slate-800' : 'border-slate-100'}`}>
          <button
            onClick={() => setSelectedNode(null)}
            className={`text-xs border rounded-lg px-2 py-1 transition-all active:scale-95 font-normal ${isDark ? 'text-slate-400 hover:text-slate-200 border-slate-700 hover:border-slate-600 bg-slate-950/20' : 'text-slate-400 hover:text-slate-600 border-slate-200 hover:border-slate-300'
              }`}
          >
            {t('common.clear')}
          </button>
          <h3 className={`text-lg font-bold ${isDark ? 'text-slate-100' : 'text-slate-800'}`}>{t('graph.nodePanel.title')}</h3>
        </div>

        <div className="mb-6 space-y-3">
          <div className={`flex justify-between items-center p-2.5 rounded-xl border ${isDark ? 'bg-slate-950/80 border-slate-800/80' : 'bg-slate-50 border-slate-100'
            }`}>
            <span className={`text-sm font-semibold ${isDark ? 'text-slate-200' : 'text-slate-800'}`}>{selectedNode.label}</span>
            <span className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'} font-medium`}>{t('graph.nodePanel.name')}</span>
          </div>
          <div className={`flex justify-between items-center p-2.5 rounded-xl border ${isDark ? 'bg-slate-950/80 border-slate-800/80' : 'bg-slate-50 border-slate-100'
            }`}>
            <div className="flex items-center gap-1.5">
              {getIconForType(selectedNode.type)}
              <span className={`text-xs capitalize font-medium ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>{selectedNode.type || 'Entity'}</span>
            </div>
            <span className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'} font-medium`}>{t('graph.nodePanel.type')}</span>
          </div>

          {selectedNode.year_hijri !== undefined && selectedNode.year_hijri !== null && (
            <div className={`flex justify-between items-center p-2.5 rounded-xl border ${isDark ? 'bg-slate-950/80 border-slate-800/80' : 'bg-slate-50 border-slate-100'}`}>
              <span className={`text-xs ${isDark ? 'text-slate-200' : 'text-slate-800'} font-semibold`}>{formatYear(selectedNode.year_hijri, 'hijri', language)}</span>
              <span className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'} font-medium`}>{t('graph.nodePanel.yearHijri')}</span>
            </div>
          )}
          {selectedNode.year_gregorian !== undefined && selectedNode.year_gregorian !== null && (
            <div className={`flex justify-between items-center p-2.5 rounded-xl border ${isDark ? 'bg-slate-950/80 border-slate-800/80' : 'bg-slate-50 border-slate-100'}`}>
              <span className={`text-xs ${isDark ? 'text-slate-200' : 'text-slate-800'} font-semibold`}>{formatYear(selectedNode.year_gregorian, 'gregorian', language)}</span>
              <span className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'} font-medium`}>{t('graph.nodePanel.yearGregorian')}</span>
            </div>
          )}
          {selectedNode.century_gregorian !== undefined && selectedNode.century_gregorian !== null && (
            <div className={`flex justify-between items-center p-2.5 rounded-xl border ${isDark ? 'bg-slate-950/80 border-slate-800/80' : 'bg-slate-50 border-slate-100'}`}>
              <span className={`text-xs ${isDark ? 'text-slate-200' : 'text-slate-800'} font-semibold`}>{formatCentury(selectedNode.century_gregorian, language)}</span>
              <span className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'} font-medium`}>{t('graph.nodePanel.centuryGregorian')}</span>
            </div>
          )}
        </div>

        <h4 className={`text-sm font-bold mb-3 ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>{t('graph.nodePanel.connections')}</h4>
        <div className={`flex-grow overflow-y-auto pr-1 space-y-2.5 [scrollbar-width:thin] ${isDark ? 'scrollbar-thumb-slate-800 [&::-webkit-scrollbar-thumb]:bg-slate-800' : ''
          } [&::-webkit-scrollbar]:w-1`}>
          {nodeConnections.length === 0 ? (
            <p className="text-slate-400 text-xs italic text-center py-4">{t('common.noData')}</p>
          ) : (
            nodeConnections.map((conn, idx) => (
              <div
                key={idx}
                onClick={() => setSelectedNode(conn.node)}
                className={`flex flex-col p-3 border rounded-xl cursor-pointer transition-all duration-200 ${isDark
                    ? 'border-slate-800/80 bg-slate-950/40 hover:bg-slate-950/80 hover:border-slate-700'
                    : 'border-slate-100 bg-slate-50 hover:bg-slate-100 hover:border-slate-300'
                  }`}
              >
                <div className="flex justify-between items-center mb-1">
                  <span className={`text-xs font-semibold ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>{conn.node.label}</span>
                  <div className="flex items-center gap-1.5">
                    <span className={`text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded ${isDark ? 'bg-slate-800 text-slate-400' : 'bg-slate-200 text-slate-600'
                      }`}>
                      {conn.direction === 'outgoing' ? '←' : '→'} {conn.label}
                    </span>
                    {isAdmin && (
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); handleDeleteRelationship(conn); }}
                        title={t('graph.admin.deleteRelationshipTitle')}
                        className="p-1 text-slate-400 hover:text-red-500 rounded-md transition-all active:scale-95"
                      >
                        <Trash2 size={12} />
                      </button>
                    )}
                  </div>
                </div>
                <div className="flex items-center justify-between mt-0.5">
                  <div className="flex items-center gap-1">
                    {getIconForType(conn.node.type)}
                    <span className="text-[10px] text-slate-400 capitalize">{conn.node.type}</span>
                  </div>
                  
                  {(conn.year_hijri !== undefined && conn.year_hijri !== null || 
                    conn.year_gregorian !== undefined && conn.year_gregorian !== null || 
                    conn.century_gregorian !== undefined && conn.century_gregorian !== null) && (
                    <div className="flex flex-wrap gap-1 justify-end text-[9px] select-none">
                      {conn.year_hijri !== undefined && conn.year_hijri !== null && (
                        <span className={`px-1 rounded font-medium ${isDark ? 'bg-amber-950/40 text-amber-400 border border-amber-900/30' : 'bg-amber-50 text-amber-700 border border-amber-100'}`}>
                          {formatYear(conn.year_hijri, 'hijri', language)}
                        </span>
                      )}
                      {conn.year_gregorian !== undefined && conn.year_gregorian !== null && (
                        <span className={`px-1 rounded font-medium ${isDark ? 'bg-sky-950/40 text-sky-400 border border-sky-900/30' : 'bg-sky-50 text-sky-700 border border-sky-100'}`}>
                          {formatYear(conn.year_gregorian, 'gregorian', language)}
                        </span>
                      )}
                      {conn.century_gregorian !== undefined && conn.century_gregorian !== null && (
                        <span className={`px-1 rounded font-medium ${isDark ? 'bg-purple-950/40 text-purple-400 border border-purple-900/30' : 'bg-purple-50 text-purple-700 border border-purple-100'}`}>
                          {formatCentury(conn.century_gregorian, language)}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    ) : (
      <div className="h-full flex flex-col items-center justify-center text-center text-slate-400 p-6 select-none animate-fade-in">
        <Network className={`mb-4 animate-pulse ${isDark ? 'text-slate-600' : 'text-slate-300'}`} size={48} />
        <h3 className={`text-base font-bold mb-2 ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>
          {t('graph.nodePanel.title')}
        </h3>
        <p className="text-xs max-w-[200px] leading-relaxed font-normal text-slate-500">
          بىلىم خەرىتىسىدىكى كۇنۇپكىلارنى چېكىپ، سۆزلۈكنىڭ تەپسىلاتى ۋە ئۆز-ئارا مۇناسىۋەتلىرىنى كۆرۈڭ.
        </p>
      </div>
    );
  };

  return (
    <div className="flex-grow flex flex-col lg:h-full lg:overflow-hidden px-4 md:px-0" dir="rtl">
      {/* Header Panel (Hidden in full screen mode to maximize canvas space) */}
      {!isFullScreen && (
        <div className="pb-6 sm:pb-8 border-b border-[#0369a1]/10 dark:border-[#38bdf8]/10 relative mb-6 sm:mb-8">
          <header className="space-y-3 sm:space-y-4">
            <div className="flex items-center gap-3 sm:gap-4 group">
              <div className="p-2 md:p-3 bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 rounded-xl shadow-lg shadow-[#0369a1]/20 dark:shadow-[#38bdf8]/10 icon-shake shrink-0">
                <Network size={20} className="md:w-6 md:h-6" strokeWidth={2.5} />
              </div>
              <div className="flex-1">
                <h1 className="text-2xl sm:text-3xl font-black text-[#1a1a1a] dark:text-slate-100">
                  {t('graph.title')}
                </h1>
                <div className="flex items-center gap-2 mt-1 sm:mt-2">
                  <span className="w-6 sm:w-8 h-[2px] bg-[#0369a1] dark:bg-[#38bdf8] rounded-full shrink-0" />
                  <p className="text-slate-500 dark:text-slate-400 text-xs sm:text-sm leading-normal">
                    {t('graph.subtitle')}
                  </p>
                </div>
              </div>
            </div>
          </header>
        </div>
      )}

      {/* Mobile Search Bar (Only shown in standard mode on small screens) */}
      {!isFullScreen && (
        <div className="lg:hidden mb-4">
          <form onSubmit={handleSearchSubmit} className="flex gap-3 w-full items-center">
            <div className="relative flex-grow group">
              <div className="absolute inset-y-0 right-4 flex items-center pointer-events-none text-[#0369a1] dark:text-[#38bdf8] transition-colors">
                <Search size={18} strokeWidth={3} />
              </div>
              <input
                type="text"
                placeholder={t('graph.searchPlaceholder')}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pr-12 pl-12 py-2.5 bg-white dark:bg-slate-900 border-2 border-[#0369a1]/10 dark:border-[#38bdf8]/10 rounded-2xl outline-none focus:border-[#0369a1] dark:focus:border-[#38bdf8] text-[#1a1a1a] dark:text-slate-100 transition-all uyghur-text shadow-sm text-base text-right font-normal"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => { setSearchQuery(''); fetchGraphData(''); }}
                  className="absolute inset-y-0 left-4 flex items-center text-[#94a3b8] hover:text-[#0369a1] dark:hover:text-[#38bdf8] transition-colors active:scale-95"
                >
                  <X size={16} strokeWidth={3} />
                </button>
              )}
            </div>
            <button
              type="submit"
              className="px-4 py-2.5 bg-gradient-to-r from-[#0369a1] to-[#0284c7] hover:from-[#0284c7] hover:to-[#0369a1] text-white rounded-2xl text-base font-semibold shadow transition-all duration-300 whitespace-nowrap active:scale-95"
            >
              {t('common.search')}
            </button>
          </form>
          {renderFilters(isThemeDark)}
        </div>
      )}

      {/* Main Layout Area */}
      <div className="flex-grow flex flex-col lg:flex-row gap-6 min-h-0 mb-6 relative">
        {/* Sidebar Info/Connections Panel (Only shown in standard mode) */}
        {!isFullScreen && (
          <div className="hidden lg:flex w-full lg:w-96 flex-col shrink-0 gap-4">
            {/* Search filter form (Desktop view - rendered above nodePanel) */}
            <form onSubmit={handleSearchSubmit} className="flex gap-3 w-full items-center">
              <div className="relative flex-grow group">
                <div className="absolute inset-y-0 right-4 flex items-center pointer-events-none text-[#0369a1] dark:text-[#38bdf8] transition-colors">
                  <Search size={18} strokeWidth={3} />
                </div>
                <input
                  type="text"
                  placeholder={t('graph.searchPlaceholder')}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pr-12 pl-12 py-2.5 bg-white dark:bg-slate-900 border-2 border-[#0369a1]/10 dark:border-[#38bdf8]/10 rounded-2xl outline-none focus:border-[#0369a1] dark:focus:border-[#38bdf8] text-[#1a1a1a] dark:text-slate-100 transition-all uyghur-text shadow-sm text-base text-right font-normal"
                />
                {searchQuery && (
                  <button
                    type="button"
                    onClick={() => { setSearchQuery(''); fetchGraphData(''); }}
                    className="absolute inset-y-0 left-4 flex items-center text-[#94a3b8] hover:text-[#0369a1] dark:hover:text-[#38bdf8] transition-colors active:scale-95"
                  >
                    <X size={16} strokeWidth={3} />
                  </button>
                )}
              </div>
              <button
                type="submit"
                className="px-4 py-2.5 bg-gradient-to-r from-[#0369a1] to-[#0284c7] hover:from-[#0284c7] hover:to-[#0369a1] text-white rounded-2xl text-base font-semibold shadow transition-all duration-300 whitespace-nowrap active:scale-95"
              >
                {t('common.search')}
              </button>
            </form>

            {/* Segmented Tab Control */}
            <div className="flex bg-slate-100 dark:bg-slate-950 p-1 rounded-xl select-none w-full border border-slate-200/50 dark:border-slate-800 shrink-0">
              <button
                type="button"
                onClick={() => setActiveTab('filters')}
                className={`flex-grow flex items-center justify-center gap-1.5 py-2 text-xs font-semibold rounded-lg transition-all duration-200 active:scale-95 ${activeTab === 'filters'
                    ? 'bg-white dark:bg-slate-800 text-[#0369a1] dark:text-[#38bdf8] shadow-sm'
                    : 'text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200'
                  }`}
              >
                {t('graph.tabFilters') || 'Filters'}
                {(selectedNodeTypes.length < availableNodeTypes.length || selectedEdgeTypes.length < availableEdgeTypes.length) && (
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0" />
                )}
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('details')}
                className={`flex-grow flex items-center justify-center gap-1.5 py-2 text-xs font-semibold rounded-lg transition-all duration-200 active:scale-95 ${activeTab === 'details'
                    ? 'bg-white dark:bg-slate-800 text-[#0369a1] dark:text-[#38bdf8] shadow-sm'
                    : 'text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200'
                  }`}
              >
                {t('graph.tabDetails') || 'Details'}
                {selectedNode && (
                  <span className="w-1.5 h-1.5 rounded-full bg-[#0369a1] dark:bg-[#38bdf8] shrink-0" />
                )}
              </button>
            </div>

            {activeTab === 'filters' ? (
              renderFilters(isThemeDark, true)
            ) : (
              <div className="flex-grow border border-[#0369a1]/10 dark:border-[#38bdf8]/10 bg-white dark:bg-slate-900 rounded-2xl p-6 shadow-md flex flex-col min-h-0">
                {renderDetailsPanelContent(isThemeDark)}
              </div>
            )}
          </div>
        )}

        {/* Graph Canvas Panel */}
        <div
          ref={containerRef}
          className={
            isFullScreen
              ? "fixed inset-0 z-[150] w-screen h-screen bg-slate-950 overflow-hidden flex flex-col justify-center items-center animate-fade-in"
              : "flex-grow border border-[#0369a1]/10 rounded-2xl bg-slate-950 overflow-hidden relative min-h-[350px] sm:min-h-[400px] lg:min-h-0 flex flex-col justify-center items-center shadow-lg animate-fade-in"
          }
        >
          {loading && (
            <div className="absolute inset-0 bg-slate-950/60 backdrop-blur-sm z-[160] flex flex-col items-center justify-center gap-3">
              <Loader2 className="animate-spin text-amber-400" size={40} />
              <span className="text-sm font-medium text-slate-300 tracking-wider">
                {t('graph.loading')}
              </span>
            </div>
          )}

          {!loading && rawGraphData.nodes.length === 0 && (
            <div className="text-center p-8 z-10 text-slate-400 animate-fade-in">
              <Network size={48} className="mx-auto mb-4 text-slate-600 animate-pulse" />
              <p className="text-lg font-medium">{t('graph.noData')}</p>
            </div>
          )}

          {rawGraphData.nodes.length > 0 && (
            <ForceGraph2D
              ref={fgRef}
              graphData={filteredData}
              width={dimensions.width}
              height={dimensions.height}
              backgroundColor="#020617" // tailwind slate-950
              cooldownTicks={120} // physics stabilization timeout
              linkWidth={1.5}
              linkColor={() => 'rgba(148, 163, 184, 0.25)'} // slate-400 opacity
              linkDirectionalArrowLength={4}
              linkDirectionalArrowColor={() => 'rgba(148, 163, 184, 0.4)'}
              linkDirectionalArrowRelPos={1}
              onNodeClick={(node: any) => setSelectedNode(node)}
              nodeCanvasObject={(node: any, ctx, globalScale) => {
                const label = node.label;
                const fontSize = 11 / globalScale;
                ctx.font = `${fontSize}px system-ui, sans-serif`;
                const textWidth = ctx.measureText(label).width;
                const bBox = [textWidth + 6, fontSize + 4];

                // Render node circle
                ctx.fillStyle = node.color || '#94a3b8';
                ctx.beginPath();
                ctx.arc(node.x, node.y, 5, 0, 2 * Math.PI, false);
                ctx.fill();

                // Highlight selected node
                if (selectedNode && selectedNode.id === node.id) {
                  ctx.strokeStyle = '#f43f5e'; // Rose-500
                  ctx.lineWidth = 2 / globalScale;
                  ctx.beginPath();
                  ctx.arc(node.x, node.y, 7, 0, 2 * Math.PI, false);
                  ctx.stroke();
                }

                // Render labels wrapper on zoom or selection
                if (globalScale >= 0.8 || (selectedNode && selectedNode.id === node.id)) {
                  ctx.fillStyle = 'rgba(15, 23, 42, 0.85)';
                  ctx.fillRect(node.x - bBox[0] / 2, node.y - 12 - bBox[1] / 2, bBox[0], bBox[1]);

                  ctx.textAlign = 'center';
                  ctx.textBaseline = 'middle';
                  ctx.fillStyle = '#f8fafc';
                  ctx.fillText(label, node.x, node.y - 12);
                }
              }}
              linkCanvasObjectMode={() => 'after'}
              linkCanvasObject={(link: any, ctx, globalScale) => {
                if (globalScale < 1.5) return; // Only show relationship types when zoomed in
                const start = link.source;
                const end = link.target;

                if (typeof start !== 'object' || typeof end !== 'object') return;

                const textPos = {
                  x: start.x + (end.x - start.x) / 2,
                  y: start.y + (end.y - start.y) / 2,
                };

                const relAngle = Math.atan2(end.y - start.y, end.x - start.x);
                const fontSize = 10 / globalScale;
                ctx.font = `${fontSize}px system-ui, sans-serif`;

                ctx.save();
                ctx.translate(textPos.x, textPos.y);
                ctx.rotate(relAngle);
                ctx.fillStyle = 'rgba(241, 245, 249, 0.6)'; // slate-100
                ctx.textAlign = 'center';
                ctx.fillText(link.label || 'RELATED_TO', 0, -3);
                ctx.restore();
              }}
            />
          )}

          {/* Floating Search Bar (Only shown in full screen mode, positioned top-right for RTL balance) */}
          {isFullScreen && (
            <div className="absolute top-4 right-4 z-[170] w-72 md:w-80 max-h-[calc(100vh-15rem)] flex flex-col min-h-0 shadow-2xl animate-fade-in">
              <form onSubmit={handleSearchSubmit} className="flex gap-3 bg-slate-900/90 border-2 border-slate-700/60 p-2 rounded-2xl backdrop-blur-md items-center shrink-0">
                <div className="relative flex-grow group">
                  <div className="absolute inset-y-0 right-4 flex items-center pointer-events-none text-slate-400">
                    <Search size={18} strokeWidth={3} />
                  </div>
                  <input
                    type="text"
                    placeholder={t('graph.searchPlaceholder')}
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full pr-12 pl-12 py-2 border-2 border-slate-800 rounded-2xl bg-slate-950 text-slate-100 placeholder-slate-500 focus:border-[#0284c7] focus:outline-none text-sm text-right font-normal shadow-inner transition-all"
                  />
                  {searchQuery && (
                    <button
                      type="button"
                      onClick={() => { setSearchQuery(''); fetchGraphData(''); }}
                      className="absolute inset-y-0 left-4 flex items-center text-slate-500 hover:text-slate-300 transition-colors active:scale-95"
                    >
                      <X size={16} strokeWidth={3} />
                    </button>
                  )}
                </div>
                <button
                  type="submit"
                  className="px-4 py-2 bg-gradient-to-r from-[#0284c7] to-[#0369a1] hover:from-[#0369a1] hover:to-[#0284c7] text-white rounded-2xl text-sm font-semibold shadow transition-all duration-300 whitespace-nowrap active:scale-95"
                >
                  {t('common.search')}
                </button>
              </form>
              {renderFilters(true)}
            </div>
          )}

          {/* Floating Details / Connections Panel (Only shown in full screen mode, positioned top-left for RTL balance) */}
          {isFullScreen && (
            <div className="hidden md:flex absolute top-4 left-4 z-[170] w-80 md:w-96 max-h-[calc(100vh-8rem)] flex-col shadow-2xl animate-fade-in">
              <div className="flex-grow border border-slate-700/60 bg-slate-900/95 backdrop-blur-md rounded-2xl p-6 flex flex-col min-h-0 text-slate-100">
                {renderDetailsPanelContent(true)}
              </div>
            </div>
          )}

          {/* Zoom, Reset & Fullscreen Floating Controls */}
          <div className="absolute left-4 bottom-4 flex flex-row gap-2 z-[170]">
            <button
              onClick={zoomIn}
              className="p-2.5 bg-slate-900/90 hover:bg-slate-800 border border-slate-700/60 rounded-xl text-slate-300 shadow hover:text-white transition-all active:scale-90"
              title="Zoom In"
            >
              <ZoomIn size={18} />
            </button>
            <button
              onClick={zoomOut}
              className="p-2.5 bg-slate-900/90 hover:bg-slate-800 border border-slate-700/60 rounded-xl text-slate-300 shadow hover:text-white transition-all active:scale-90"
              title="Zoom Out"
            >
              <ZoomOut size={18} />
            </button>
            <button
              onClick={resetZoom}
              className="p-2.5 bg-slate-900/90 hover:bg-slate-800 border border-slate-700/60 rounded-xl text-slate-300 shadow hover:text-white transition-all active:scale-90"
              title="Reset View"
            >
              <Maximize2 size={18} />
            </button>
            <button
              onClick={() => setIsFullScreen(!isFullScreen)}
              className="p-2.5 bg-slate-900/90 hover:bg-slate-800 border border-slate-700/60 rounded-xl text-slate-300 shadow hover:text-white transition-all active:scale-90"
              title={isFullScreen ? t('graph.exitFullscreen') || 'Exit Fullscreen' : t('graph.enterFullscreen') || 'Fullscreen'}
            >
              {isFullScreen ? <Minimize size={18} /> : <Maximize size={18} />}
            </button>
          </div>

          {/* Graph Legend Panel */}
          <div className="absolute right-4 bottom-4 bg-slate-900/90 border border-slate-700/60 rounded-2xl p-3 text-xs font-normal text-slate-300 flex flex-col gap-2 shadow-2xl z-[170] select-none max-w-[200px]">
            <div
              onClick={() => setShowLegend(!showLegend)}
              className="flex items-center justify-between gap-4 cursor-pointer hover:text-white transition-colors"
            >
              <div className="flex items-center gap-1.5 font-bold text-slate-200">
                <HelpCircle size={13} />
                <span>{language === 'ug' ? 'تۈر كۆرسەتكۈچى' : 'Legend'}</span>
              </div>
              <ChevronDown
                size={13}
                className={`transition-transform duration-300 ${showLegend ? 'rotate-180' : 'rotate-0'}`}
              />
            </div>

            {showLegend && (
              <div className="flex flex-col gap-2.5 mt-1.5 animate-fade-in">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-amber-400" />
                  <span>Person (شەخس)</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-sky-400" />
                  <span>Location (ئورۇن)</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-400" />
                  <span>Organization (تەشكىلات)</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-rose-400" />
                  <span>Event (ۋەقە)</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-purple-400" />
                  <span>Historical Era (تارىخىي دەۋر)</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-indigo-400" />
                  <span>Concept (ئۇقۇم)</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-slate-400" />
                  <span>Other (باشقىلار)</span>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Mobile slide-up details drawer */}
      {selectedNode && (
        <div className="lg:hidden fixed inset-0 z-[200] flex flex-col justify-end">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm animate-fade-in"
            onClick={() => setSelectedNode(null)}
          />

          {/* Bottom Sheet */}
          <div className="relative w-full max-h-[70vh] bg-white rounded-t-[32px] px-6 pb-6 pt-4 flex flex-col min-h-0 shadow-[0_-12px_48px_rgba(0,0,0,0.15)] border-t border-[#0369a1]/10 animate-slide-up" dir="rtl">
            {/* Grab handle */}
            <div className="w-12 h-1.5 bg-slate-200 rounded-full mx-auto mb-4 shrink-0" />

            {/* Content */}
            <div className="flex-grow overflow-y-auto [scrollbar-width:thin] pr-1">
              {renderDetailsPanelContent(false)}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
