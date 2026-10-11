<template><component :is="glyph" :size="18" :stroke-width="1.65" aria-hidden="true"/></template>
<script setup lang="ts">
import {computed,type Component} from 'vue';
import {MessageSquare,BookOpen,Settings,Plus,ArrowUp,Square,Trash2,Pencil,
 ChevronDown,ChevronRight,ChevronLeft,Search,X,Check,Download,Upload,RotateCw,
 Copy,Menu,LogOut,Sparkles,FileText,Link,Folder,Eye,EyeOff,TriangleAlert,PanelRight,
 Bookmark,UserRound,LockKeyhole,Mail,Network,Plug,ThumbsUp,
 ThumbsDown,Paperclip,Ellipsis,PanelLeft,ShieldCheck,CheckCircle2,ExternalLink} from 'lucide-vue-next';
const props=defineProps<{name:string}>();
const icons:Record<string,Component>={chat:MessageSquare,book:BookOpen,
 settings:Settings,plus:Plus,send:ArrowUp,stop:Square,trash:Trash2,
 edit:Pencil,chevronDown:ChevronDown,chevronRight:ChevronRight,
 chevronLeft:ChevronLeft,search:Search,x:X,check:Check,upload:Upload,
 refresh:RotateCw,copy:Copy,menu:Menu,logout:LogOut,spark:Sparkles,doc:FileText,link:Link,
 folder:Folder,eye:Eye,eyeOff:EyeOff,alert:TriangleAlert,panel:PanelRight,
 citation:Bookmark,user:UserRound,lock:LockKeyhole,mail:Mail,
 graph:Network,export:Download,plug:Plug,thumbUp:ThumbsUp,thumbDown:ThumbsDown,
 attachment:Paperclip,more:Ellipsis,sidebar:PanelLeft,shield:ShieldCheck,
 success:CheckCircle2,external:ExternalLink};
const glyph=computed(()=>icons[props.name]||FileText);
</script>
