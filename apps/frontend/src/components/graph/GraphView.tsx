import React, { useEffect, useState, useRef, useMemo } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { useI18n } from '../../i18n/I18nContext';
import { Search, Loader2, ZoomIn, ZoomOut, Maximize, Minimize, Maximize2, Network, BookOpen, MapPin, User, Calendar, HelpCircle, X, SlidersHorizontal } from 'lucide-react';

interface GraphNode {
  id: string;
  label: string;
  type: string;
  x?: number;
  y?: number;
  color?: string;
}

interface GraphLink {
  source: any;
  target: any;
  label: string;
}

interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

export const GraphView: React.FC = () => {
  const { t, language } = useI18n();
  const [rawGraphData, setRawGraphData] = useState<GraphData>({ nodes: [], links: [] });
  const [selectedNodeTypes, setSelectedNodeTypes] = useState<string[]>([]);
  const [selectedEdgeTypes, setSelectedEdgeTypes] = useState<string[]>([]);
  const [activeTab, setActiveTab] = useState<'details' | 'filters'>('filters');
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [nodeConnections, setNodeConnections] = useState<any[]>([]);
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
        } else if (type.includes('book') || type.includes('ئەسەر') || type.includes('قىسسە')) {
          color = '#c084fc'; // Purple
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
    if (tVal.includes('book') || tVal.includes('ئەسەر')) return 'bg-purple-400 text-white border-purple-500 hover:bg-purple-300';
    return 'bg-slate-400 text-slate-950 border-slate-500 hover:bg-slate-300';
  };

  const renderFilters = (isDark: boolean, isSidebar = false) => {
    if (availableNodeTypes.length === 0 && availableEdgeTypes.length === 0) return null;

    const containerStyle = isDark
      ? 'border-slate-800 bg-slate-900/90 text-slate-100 backdrop-blur-md mt-3 w-full p-4'
      : isSidebar
        ? 'border-[#0369a1]/10 bg-white text-slate-800 flex-grow min-h-0 flex flex-col h-full w-full shadow-md p-6'
        : 'border-[#0369a1]/10 bg-white text-slate-800 mt-2 w-full shadow-md p-4';

    return (
      <div className={`border rounded-2xl flex flex-col gap-4 shadow-sm select-none transition-all duration-300 ${containerStyle}`}>
        {/* Header */}
        <div className="flex items-center justify-between border-b pb-2 mb-1 border-slate-100/10">
          <div className="flex items-center gap-2">
            <SlidersHorizontal size={14} className={isDark ? 'text-slate-400' : 'text-[#0369a1]'} />
            <span className="text-xs font-bold">{t('graph.filterNodeTypes') || 'Filters'}</span>
          </div>
          {/* Reset / All buttons */}
          <div className="flex gap-2">
            <button
              onClick={() => {
                setSelectedNodeTypes(availableNodeTypes);
                setSelectedEdgeTypes(availableEdgeTypes);
              }}
              type="button"
              className={`text-[10px] px-2 py-0.5 rounded border transition-all active:scale-95 ${
                isDark 
                  ? 'border-slate-700 text-slate-400 hover:text-slate-200 hover:border-slate-600 bg-slate-800/50' 
                  : 'border-slate-200 text-slate-500 hover:text-[#0369a1] hover:border-[#0369a1]/30 bg-slate-50'
              }`}
            >
              {t('graph.all') || 'All'}
            </button>
            <button
              onClick={() => {
                setSelectedNodeTypes([]);
                setSelectedEdgeTypes([]);
              }}
              type="button"
              className={`text-[10px] px-2 py-0.5 rounded border transition-all active:scale-95 ${
                isDark 
                  ? 'border-slate-700 text-slate-400 hover:text-slate-200 hover:border-slate-600 bg-slate-800/50' 
                  : 'border-slate-200 text-slate-500 hover:text-red-500 hover:border-red-200 bg-slate-50'
              }`}
            >
              {language === 'ug' ? 'سۈزۈۋېتىش' : 'Clear'}
            </button>
          </div>
        </div>

        {/* Node Types Section */}
        {availableNodeTypes.length > 0 && (
          <div className="flex flex-col gap-1.5 font-normal">
            <span className={`text-[10px] font-semibold uppercase tracking-wider ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
              {t('graph.filterNodeTypes') || 'Entity Types'}
            </span>
            <div className="flex flex-wrap gap-1.5">
              {availableNodeTypes.map(type => {
                const isActive = selectedNodeTypes.includes(type);
                return (
                  <button
                    key={type}
                    type="button"
                    onClick={() => toggleNodeType(type)}
                    className={`flex items-center gap-1 px-2.5 py-1 text-xs font-semibold rounded-xl border transition-all duration-200 active:scale-95 ${
                      isActive 
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

        {/* Edge Types Section */}
        {availableEdgeTypes.length > 0 && (
          <div className={`flex flex-col gap-1.5 border-t border-slate-100/10 pt-2.5 ${
            isSidebar ? 'min-h-0 flex-grow' : ''
          }`}>
            <span className={`text-[10px] font-semibold uppercase tracking-wider ${isDark ? 'text-slate-400' : 'text-slate-500'}`}>
              {t('graph.filterEdgeTypes') || 'Relationship Types'}
            </span>
            <div className={`flex flex-wrap gap-1.5 overflow-y-auto pr-1 [scrollbar-width:thin] ${
              isSidebar ? 'flex-grow min-h-0' : 'max-h-52'
            } ${
              isDark 
                ? 'scrollbar-thumb-slate-800 [&::-webkit-scrollbar-thumb]:bg-slate-800' 
                : 'scrollbar-thumb-slate-200 [&::-webkit-scrollbar-thumb]:bg-slate-200'
            } [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-thumb]:rounded`}>
              {availableEdgeTypes.map(type => {
                const isActive = selectedEdgeTypes.includes(type);
                const displayName = type.replace(/_/g, ' ');
                return (
                  <button
                    key={type}
                    type="button"
                    onClick={() => toggleEdgeType(type)}
                    className={`px-2.5 py-1 text-xs font-semibold rounded-xl border transition-all duration-200 active:scale-95 ${
                      isActive 
                        ? isDark
                          ? 'bg-indigo-50/20 text-indigo-400 border-indigo-500/40 hover:bg-indigo-500/30'
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

  // Prevent scroll when fullscreen
  useEffect(() => {
    if (isFullScreen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
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
        node: targetNode || { id: targetNodeId, label: targetNodeId, type: 'Unknown' }
      };
    });
    setNodeConnections(connections);
  }, [selectedNode, filteredData]);

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
    if (t.includes('event') || t.includes('ۋەقە')) return <Calendar size={14} className="text-rose-400" />;
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
            className={`text-xs border rounded-lg px-2 py-1 transition-all active:scale-95 font-normal ${
              isDark ? 'text-slate-400 hover:text-slate-200 border-slate-700 hover:border-slate-600 bg-slate-950/20' : 'text-slate-400 hover:text-slate-600 border-slate-200 hover:border-slate-300'
            }`}
          >
            {t('common.clear')}
          </button>
          <h3 className={`text-lg font-bold ${isDark ? 'text-slate-100' : 'text-slate-800'}`}>{t('graph.nodePanel.title')}</h3>
        </div>

        <div className="mb-6 space-y-3">
          <div className={`flex justify-between items-center p-2.5 rounded-xl border ${
            isDark ? 'bg-slate-950/80 border-slate-800/80' : 'bg-slate-50 border-slate-100'
          }`}>
            <span className={`text-sm font-semibold ${isDark ? 'text-slate-200' : 'text-slate-800'}`}>{selectedNode.label}</span>
            <span className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'} font-medium`}>{t('graph.nodePanel.name')}</span>
          </div>
          <div className={`flex justify-between items-center p-2.5 rounded-xl border ${
            isDark ? 'bg-slate-950/80 border-slate-800/80' : 'bg-slate-50 border-slate-100'
          }`}>
            <div className="flex items-center gap-1.5">
              {getIconForType(selectedNode.type)}
              <span className={`text-xs capitalize font-medium ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>{selectedNode.type || 'Entity'}</span>
            </div>
            <span className={`text-xs ${isDark ? 'text-slate-400' : 'text-slate-500'} font-medium`}>{t('graph.nodePanel.type')}</span>
          </div>
        </div>

        <h4 className={`text-sm font-bold mb-3 ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>{t('graph.nodePanel.connections')}</h4>
        <div className={`flex-grow overflow-y-auto pr-1 space-y-2.5 [scrollbar-width:thin] ${
          isDark ? 'scrollbar-thumb-slate-800 [&::-webkit-scrollbar-thumb]:bg-slate-800' : ''
        } [&::-webkit-scrollbar]:w-1`}>
          {nodeConnections.length === 0 ? (
            <p className="text-slate-400 text-xs italic text-center py-4">{t('common.noData')}</p>
          ) : (
            nodeConnections.map((conn, idx) => (
              <div 
                key={idx}
                onClick={() => setSelectedNode(conn.node)}
                className={`flex flex-col p-3 border rounded-xl cursor-pointer transition-all duration-200 ${
                  isDark 
                    ? 'border-slate-800/80 bg-slate-950/40 hover:bg-slate-950/80 hover:border-slate-700' 
                    : 'border-slate-100 bg-slate-50 hover:bg-slate-100 hover:border-slate-300'
                }`}
              >
                <div className="flex justify-between items-center mb-1">
                  <span className={`text-xs font-semibold ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>{conn.node.label}</span>
                  <span className={`text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded ${
                    isDark ? 'bg-slate-800 text-slate-400' : 'bg-slate-200 text-slate-600'
                  }`}>
                    {conn.direction === 'outgoing' ? '←' : '→'} {conn.label}
                  </span>
                </div>
                <div className="flex items-center gap-1 mt-0.5">
                  {getIconForType(conn.node.type)}
                  <span className="text-[10px] text-slate-400 capitalize">{conn.node.type}</span>
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
        <div className="mb-6">
          <h1 className="text-2xl md:text-3xl font-bold text-slate-800 tracking-tight flex items-center gap-3">
            <span className="p-2 bg-gradient-to-tr from-amber-400 to-purple-500 rounded-xl text-white">
              <Network size={28} />
            </span>
            {t('graph.title')}
          </h1>
          <p className="text-slate-500 text-sm mt-1">
            {t('graph.subtitle')}
          </p>
        </div>
      )}

      {/* Mobile Search Bar (Only shown in standard mode on small screens) */}
      {!isFullScreen && (
        <div className="lg:hidden mb-4">
          <form onSubmit={handleSearchSubmit} className="flex gap-3 w-full items-center">
            <div className="relative flex-grow group">
              <div className="absolute inset-y-0 right-4 flex items-center pointer-events-none text-[#0369a1] transition-colors">
                <Search size={18} strokeWidth={3} />
              </div>
              <input
                type="text"
                placeholder={t('graph.searchPlaceholder')}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pr-12 pl-12 py-2.5 bg-white border-2 border-[#0369a1]/10 rounded-2xl outline-none focus:border-[#0369a1] transition-all uyghur-text shadow-sm text-base text-right font-normal"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => { setSearchQuery(''); fetchGraphData(''); }}
                  className="absolute inset-y-0 left-4 flex items-center text-[#94a3b8] hover:text-[#0369a1] transition-colors active:scale-95"
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
          {renderFilters(false)}
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
                <div className="absolute inset-y-0 right-4 flex items-center pointer-events-none text-[#0369a1] transition-colors">
                  <Search size={18} strokeWidth={3} />
                </div>
                <input
                  type="text"
                  placeholder={t('graph.searchPlaceholder')}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pr-12 pl-12 py-2.5 bg-white border-2 border-[#0369a1]/10 rounded-2xl outline-none focus:border-[#0369a1] transition-all uyghur-text shadow-sm text-base text-right font-normal"
                />
                {searchQuery && (
                  <button
                    type="button"
                    onClick={() => { setSearchQuery(''); fetchGraphData(''); }}
                    className="absolute inset-y-0 left-4 flex items-center text-[#94a3b8] hover:text-[#0369a1] transition-colors active:scale-95"
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
            <div className="flex bg-slate-100 p-1 rounded-xl select-none w-full border border-slate-200/50">
              <button
                type="button"
                onClick={() => setActiveTab('filters')}
                className={`flex-grow py-2 text-xs font-semibold rounded-lg transition-all duration-200 active:scale-95 ${
                  activeTab === 'filters'
                    ? 'bg-white text-[#0369a1] shadow-sm'
                    : 'text-slate-500 hover:text-slate-800'
                }`}
              >
                {t('graph.tabFilters') || 'Filters'}
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('details')}
                className={`flex-grow py-2 text-xs font-semibold rounded-lg transition-all duration-200 active:scale-95 ${
                  activeTab === 'details'
                    ? 'bg-white text-[#0369a1] shadow-sm'
                    : 'text-slate-500 hover:text-slate-800'
                }`}
              >
                {t('graph.tabDetails') || 'Details'}
              </button>
            </div>

            {activeTab === 'filters' ? (
              renderFilters(false, true)
            ) : (
              <div className="flex-grow border border-[#0369a1]/10 bg-white rounded-2xl p-6 shadow-md flex flex-col min-h-0">
                {renderDetailsPanelContent(false)}
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
                ctx.arc(node.x, node.y, 6, 0, 2 * Math.PI, false);
                ctx.fill();

                // Highlight selected node
                if (selectedNode && selectedNode.id === node.id) {
                  ctx.strokeStyle = '#f43f5e'; // Rose-500
                  ctx.lineWidth = 2 / globalScale;
                  ctx.beginPath();
                  ctx.arc(node.x, node.y, 9, 0, 2 * Math.PI, false);
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
                const fontSize = 8 / globalScale;
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

          {/* Floating Search Bar (Only shown in full screen mode, positioned top-left for RTL balance) */}
          {isFullScreen && (
            <div className="absolute top-4 left-4 z-[170] w-72 md:w-80 shadow-2xl animate-fade-in">
              <form onSubmit={handleSearchSubmit} className="flex gap-3 bg-slate-900/90 border-2 border-slate-700/60 p-2 rounded-2xl backdrop-blur-md items-center">
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

          {/* Floating Details / Connections Panel (Only shown in full screen mode, positioned top-right for RTL balance) */}
          {isFullScreen && (
            <div className="hidden md:flex absolute top-4 right-4 z-[170] w-80 md:w-96 max-h-[calc(100vh-8rem)] flex-col shadow-2xl animate-fade-in">
              <div className="flex-grow border border-slate-700/60 bg-slate-900/95 backdrop-blur-md rounded-2xl p-6 flex flex-col min-h-0 text-slate-100">
                {renderDetailsPanelContent(true)}
              </div>
            </div>
          )}

          {/* Zoom, Reset & Fullscreen Floating Controls */}
          <div className="absolute left-4 bottom-4 flex flex-col gap-2 z-[170]">
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
          <div className="absolute right-4 bottom-4 bg-slate-900/90 border border-slate-700/60 rounded-2xl p-4 text-xs font-normal text-slate-300 flex flex-col gap-2.5 shadow-2xl z-[170] select-none">
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
              <span>Book (ئەسەر)</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
